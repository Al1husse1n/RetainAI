"""
Dashboard + SSE stream for the Ollama-backed campaign pipeline.
Each tool is invoked separately; the client receives step-by-step events.
Terminal: every SSE event is printed (set RETAIN_SSE_PRINT=0 to disable).
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, Generator, Iterator, List

from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from main.agents.compliant_agent import run_agent as run_complaint_agent
from main.agents.tools import (
    decide_strategy,
    extract_guest_filters,
    filter_guests,
    generate_email,
    merge_with_manual_filters,
    send_campaign,
)
from main.sse_utils import format_sse


_SSE_PRINT = os.environ.get("RETAIN_SSE_PRINT", "1") != "0"


def _sse_emit(data: Dict[str, Any]) -> str:
    """Format one SSE message and mirror it to the runserver terminal for debugging."""
    if _SSE_PRINT:
        t = data.get("type", "?")
        if t == "log":
            print(f"[SSE] {data.get('message', '')}", flush=True)
        elif t == "guests":
            print(f"[SSE] guests count={data.get('count')} (list payload sent)", flush=True)
        elif t == "email_preview":
            g = data.get("guest") or {}
            em = data.get("email") or {}
            print(
                f"[SSE] email_preview → {g.get('name', '?')} | subject={str(em.get('subject', ''))[:60]}",
                flush=True,
            )
        elif t == "done":
            print("[SSE] done", flush=True)
        elif t == "error":
            print(f"[SSE] ERROR {data.get('message', '')}", flush=True)
        else:
            print(f"[SSE] {t}", flush=True)
    return format_sse(data)


def landing(request):
    return render(request, "main/landing.html")


def dashboard(request):
    return render(request, "main/dashboard.html")


def _parse_manual_filters(request) -> Dict[str, Any]:
    raw = request.GET.get("filters", "{}")
    try:
        ui = json.loads(raw)
    except json.JSONDecodeError:
        ui = {}
    if not isinstance(ui, dict):
        return {}
    return _normalize_ui_filters(ui)


def _normalize_ui_filters(ui: Dict[str, Any]) -> Dict[str, Any]:
    """Map dashboard dropdown labels to tool filter keys."""
    out: Dict[str, Any] = {}
    lv = str(ui.get("last_visit", "")).strip()
    if lv == "Last 7 Days":
        out["max_days_since_last_visit"] = 7
    elif lv == "Last 30 Days":
        out["max_days_since_last_visit"] = 30
    sp = str(ui.get("spend", "")).strip()
    if sp == "$500+":
        out["min_spend"] = 500.0
    elif sp == "$1k+":
        out["min_spend"] = 1000.0
    cm = str(ui.get("complaint", "")).strip()
    if cm == "No":
        out["max_complaint_count"] = 0
    elif cm == "Yes":
        out["min_complaint_count"] = 1
    gt = str(ui.get("guest_type", "")).strip()
    if gt and gt != "All Types":
        out["guest_types"] = [gt]
    sl = str(ui.get("send_limit", "")).strip()
    if sl and sl != "No Limit" and sl.isdigit():
        out["send_limit"] = int(sl)
    return out


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return _json_safe_value(value.item())
        except Exception:
            return value
    if isinstance(value, dict):
        return {k: _json_safe_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(v) for v in value]
    return value


def _serialize_guest(g: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _json_safe_value(v) for k, v in g.items()}


def _campaign_event_stream(
    query: str, manual: Dict[str, Any], max_emails: int
) -> Iterator[str]:
    if not query.strip():
        yield _sse_emit({"type": "error", "message": "Campaign query is empty."})
        return

    try:
        yield _sse_emit({"type": "log", "message": "🔍 Extracting filters..."})
        extracted = extract_guest_filters.invoke({"campaign_description": query})
        yield _sse_emit(
            {"type": "log", "message": "🔍 Extracted AI filter suggestions.", "data": {"extracted": extracted}}
        )

        yield _sse_emit({"type": "log", "message": "🔀 Merging with manual filters..."})
        merged = merge_with_manual_filters.invoke(
            {"extracted_filters": extracted, "manual_filters": manual}
        )
        yield _sse_emit({"type": "log", "message": "🔀 Filters merged.", "data": {"merged": merged}})

        yield _sse_emit({"type": "log", "message": "👥 Filtering guests (demo_guests)..."})
        guests: List[Dict[str, Any]] = filter_guests.invoke({"filters": merged})
        n = len(guests)
        yield _sse_emit({"type": "log", "message": f"👥 Found {n} guests...", "data": {"count": n}})
        yield _sse_emit(
            {"type": "guests", "guests": [_serialize_guest(g) for g in guests], "count": n}
        )

        if not guests:
            yield _sse_emit({"type": "log", "message": "⚠️ No guests matched."})
            yield _sse_emit({"type": "done"})
            return

        if max_emails > 0 and len(guests) > max_emails:
            guests = guests[:max_emails]
            yield _sse_emit({"type": "log", "message": f"✂️ Capping at {max_emails} guests (speed)."})

        yield _sse_emit({"type": "log", "message": "🧠 Deciding strategy..."})
        strategy = decide_strategy.invoke(
            {"campaign_description": query, "target_guests": guests}
        )
        label = strategy.get("strategy", "")
        yield _sse_emit(
            {
                "type": "log",
                "message": f"🧠 Strategy selected: {label}",
                "data": {"strategy": _json_safe_value(strategy)},
            }
        )

        emails: List[Dict[str, Any]] = []
        for g in guests:
            nm = g.get("name") or "Guest"
            yield _sse_emit({"type": "log", "message": f"📧 Writing email for {nm}..."})
            em = generate_email.invoke(
                {"guest": g, "campaign_description": query, "strategy": strategy}
            )
            emails.append(em)
            yield _sse_emit(
                {
                    "type": "email_preview",
                    "email": _json_safe_value(em),
                    "guest": _serialize_guest(g),
                }
            )
            yield _sse_emit(
                {
                    "type": "log",
                    "message": f"✅ Email drafted for {nm} (preview updated)",
                }
            )

        yield _sse_emit({"type": "log", "message": "📤 Sending campaign (demo)..."})
        result = send_campaign.invoke({"emails": emails})
        yield _sse_emit(
            {
                "type": "log",
                "message": f"✅ Campaign sent ({result.get('sent_count', len(emails))} messages)",
                "data": _json_safe_value(result),
            }
        )
        yield _sse_emit({"type": "done"})
    except Exception as exc:  # noqa: BLE001
        yield _sse_emit({"type": "error", "message": str(exc)})


def stream_campaign(request) -> StreamingHttpResponse:
    query = request.GET.get("query", "")
    manual = _parse_manual_filters(request)
    try:
        max_emails = int(request.GET.get("max_emails", "15"))
    except ValueError:
        max_emails = 15

    gen: Generator[str, None, None] = _campaign_event_stream(query, manual, max_emails)
    resp = StreamingHttpResponse(gen, content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp

@csrf_exempt
def get_complaint(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST is allowed."}, status=405)

    try:
        if request.content_type == "application/json":
            data = json.loads(request.body.decode("utf-8") if isinstance(request.body, bytes) else request.body)
        else:
            data = {
                "name": request.POST.get("name", "").strip(),
                "email": request.POST.get("email", "").strip(),
                "complaint": request.POST.get("complaint", "").strip(),
            }

        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip()
        complaint = (data.get("complaint") or "").strip()

        if not name or not email or not complaint:
            return JsonResponse({"error": "Missing name, email, or complaint description."}, status=400)

        result = run_complaint_agent(name, email, complaint)

        return JsonResponse(
            {
                "message": "Complaint received and resolution email processed.",
                "email": email,
                "name": name,
                "complaint": complaint,
                "result": result,
            },
            status=200,
        )
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data."}, status=400)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)
