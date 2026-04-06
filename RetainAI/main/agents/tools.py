"""
Campaign pipeline tools (LangChain @tool) backed by Google Gemini.
Uses demo_guests.csv next to this file — no discounts in generated copy (hackathon rule).
"""

from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
import pandas as pd
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# --- Paths: demo_guests.csv lives in main/agents/ ---
_AGENTS_DIR = Path(__file__).resolve().parent
_DEMO_CSV = _AGENTS_DIR / "demo_guests.csv"

_llm = None
_api_key_index = 0


def _load_google_api_keys() -> List[str]:
    keys: List[str] = []
    for name in (
        "GOOGLE_API_KEY",
        "GOOGLE_API_KEY_BACKUP_1",
        "GOOGLE_API_KEY_BACKUP_2",
    ):
        value = os.getenv(name)
        if value:
            keys.append(value.strip())
    fallback = os.getenv("GOOGLE_API_KEYS", "")
    for part in fallback.split(","):
        key = part.strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def _current_api_key() -> str:
    keys = _load_google_api_keys()
    if not keys:
        raise ValueError(
            "Set GOOGLE_API_KEY or at least one backup key like GOOGLE_API_KEY_BACKUP_1"
        )
    return keys[_api_key_index]


def _advance_api_key() -> None:
    global _api_key_index
    keys = _load_google_api_keys()
    if len(keys) <= 1:
        return
    _api_key_index = (_api_key_index + 1) % len(keys)


def _reset_llm() -> None:
    global _llm
    _llm = None


def _invoke_with_fallback(prompt: str):
    keys = _load_google_api_keys()
    last_exc: Optional[Exception] = None
    for attempt in range(len(keys)):
        try:
            return get_llm().invoke(prompt)
        except Exception as exc:
            last_exc = exc
            if attempt == len(keys) - 1:
                raise
            print(
                "Gemini API key failed, switching to next available key."
            )
            _advance_api_key()
            _reset_llm()
    raise last_exc


def get_llm():
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",  # stable model
            temperature=0.3,
            api_key=_current_api_key()
        )
    return _llm


def _infer_name_query_from_campaign(text: str) -> Optional[str]:
    """If the LLM omits name filters, recover a substring from common phrasings."""
    if not (text or "").strip():
        return None
    t = text.strip()
    patterns = (
        r"\bnamed\s+([A-Za-z][A-Za-z\-'.]+)",
        r"\bname\s+is\s+([A-Za-z][A-Za-z\-'.]+)",
        r"\bfind\s+(?:a\s+)?(?:guest\s+)?(?:named\s+)?([A-Za-z][A-Za-z\-'.]+)\b",
        r"\bfor\s+guest\s+([A-Za-z][A-Za-z\-'.]+)\b",
        r"\btell\s+([A-Za-z][A-Za-z\-'.]+)\b",
    )
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            w = m.group(1).strip()
            # Skip common English words that match "tell X"
            if w.lower() in {"him", "her", "them", "everyone", "all", "guest", "guests"}:
                continue
            if len(w) >= 2:
                return w
    return None


def extract_json_from_response(response_text: str) -> dict:
    """Parse JSON from small models (strip fences, grab first object)."""
    text = (response_text or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def load_guests() -> pd.DataFrame:
    if not _DEMO_CSV.exists():
        raise FileNotFoundError(f"CSV not found: {_DEMO_CSV}")
    df = pd.read_csv(_DEMO_CSV)
    df = df.copy()
    # Align with filter_guests expectations
    if "complaint_count" not in df.columns and "had_complaint" in df.columns:
        df["complaint_count"] = df["had_complaint"].astype(int)
    elif "complaint_count" not in df.columns:
        df["complaint_count"] = 0
    if "guest_type" not in df.columns:

        def _guest_type(row: pd.Series) -> str:
            if row.get("had_complaint"):
                return "Recovery"
            if float(row.get("total_spend") or 0) >= 2500:
                return "VIP"
            if int(row.get("visit_count") or 0) >= 4 and float(row.get("total_spend") or 0) >= 1500:
                return "Corporate"
            if int(row.get("visit_count") or 0) >= 3:
                return "Recurring"
            return "First Timer"

        df["guest_type"] = df.apply(_guest_type, axis=1)
    return df


# ----- tools -----


def _coerce_name_filter_value(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s else None


@tool
def extract_guest_filters(campaign_description: str) -> Dict[str, Any]:
    """Use Ollama to turn natural language into filter JSON."""
    prompt = f"""Today: {datetime.now().strftime("%Y-%m-%d")}
Campaign: {campaign_description}

Return ONLY a JSON object with any of these keys (omit unknowns, use null):
- min_days_since_last_visit (int): guest has not stayed for at least this many days (CSV "last_visit" is days since visit)
- max_days_since_last_visit (int): guest stayed within the last N days (last_visit <= N)
- min_spend, max_spend (numbers)
- guest_types (array of strings, e.g. ["VIP"])
- min_complaint_count, max_complaint_count (ints)
- send_limit (int): cap cohort size after other filters; sort by total_spend descending when applied
- name_contains (string): substring match on guest full name (case-insensitive), e.g. "Ali" or "Hussein"
No markdown, JSON only."""

    try:
        r = _invoke_with_fallback(prompt)
        content = r.content if hasattr(r, "content") else str(r)
        out = extract_json_from_response(str(content))
        # Normalize alternate keys small models sometimes emit
        for alias, key in (
            ("guest_name", "name_contains"),
            ("name", "name_contains"),
            ("name_query", "name_contains"),
        ):
            if alias in out and out.get(alias) and not out.get("name_contains"):
                out["name_contains"] = out.pop(alias, None)
        nc = _coerce_name_filter_value(out.get("name_contains"))
        if nc:
            out["name_contains"] = nc
        elif "name_contains" in out:
            out.pop("name_contains", None)
        # Coerce numerics
        for k in (
            "min_days_since_last_visit",
            "max_days_since_last_visit",
            "send_limit",
            "min_complaint_count",
            "max_complaint_count",
        ):
            if k in out and out[k] is not None:
                try:
                    out[k] = int(float(out[k]))
                except (TypeError, ValueError):
                    del out[k]
        for k in ("min_spend", "max_spend"):
            if k in out and out[k] is not None:
                try:
                    out[k] = float(out[k])
                except (TypeError, ValueError):
                    del out[k]
        if not out.get("name_contains"):
            inferred = _infer_name_query_from_campaign(campaign_description)
            if inferred:
                out["name_contains"] = inferred
        return out
    except Exception:
        inferred = _infer_name_query_from_campaign(campaign_description)
        return {"name_contains": inferred} if inferred else {}


@tool
def merge_with_manual_filters(
    extracted_filters: Dict[str, Any],
    manual_filters: Dict[str, Any],
) -> Dict[str, Any]:
    """Manual UI filters override AI."""
    merged = dict(extracted_filters or {})
    for k, v in (manual_filters or {}).items():
        if v is not None and str(v).strip() != "":
            merged[k] = v
    return merged


@tool
def filter_guests(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Filter demo_guests. Column last_visit = integer days since last stay.
    """
    df = load_guests()
    f = filters or {}

    if f.get("min_days_since_last_visit") is not None:
        df = df[df["last_visit"] >= int(f["min_days_since_last_visit"])]
    if f.get("max_days_since_last_visit") is not None:
        df = df[df["last_visit"] <= int(f["max_days_since_last_visit"])]
    if f.get("min_spend") is not None:
        df = df[df["total_spend"] >= float(f["min_spend"])]
    if f.get("max_spend") is not None:
        df = df[df["total_spend"] <= float(f["max_spend"])]
    if f.get("max_complaint_count") is not None:
        df = df[df["complaint_count"] <= int(f["max_complaint_count"])]
    if f.get("min_complaint_count") is not None:
        df = df[df["complaint_count"] >= int(f["min_complaint_count"])]
    if f.get("guest_types"):
        df = df[df["guest_type"].isin(list(f["guest_types"]))]
    name_q = _coerce_name_filter_value(f.get("name_contains"))
    if name_q:
        col = df["name"].astype(str)
        mask = col.str.lower().str.contains(re.escape(name_q.lower()), na=False)
        df = df[mask]
    if f.get("send_limit"):
        df = df.sort_values(by="total_spend", ascending=False).head(int(f["send_limit"]))

    return df.to_dict(orient="records")


def _campaign_implies_departure_or_boundary(campaign_description: str) -> bool:
    cd = (campaign_description or "").lower()
    phrases = (
        "not come back",
        "not to come back",
        "don't come back",
        "dont come back",
        "do not come back",
        "never come back",
        "not welcome",
        "unwelcome",
        "blacklist",
        "stay away",
        "do not return",
        "don't return",
        "dont return",
        "no longer welcome",
        "ban from",
        "trespass",
        "refuse service",
    )
    return any(p in cd for p in phrases)


def _campaign_implies_apology_or_recovery(campaign_description: str) -> bool:
    cd = (campaign_description or "").lower()
    return any(
        p in cd
        for p in (
            "apolog",
            "sorry",
            "make it right",
            "complaint",
            "service recovery",
            "incident",
        )
    )


@tool
def decide_strategy(
    campaign_description: str, target_guests: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Pick strategy from campaign intent and cohort stats (no extra LLM round-trip)."""
    if not target_guests:
        return {
            "strategy": "No guests",
            "tone": "N/A",
            "key_message": "N/A",
            "call_to_action": "N/A",
        }
    avg_spend = sum(g.get("total_spend", 0) or 0 for g in target_guests) / len(target_guests)
    vip_count = sum(1 for g in target_guests if g.get("guest_type") == "VIP")
    avg_days = sum(g.get("last_visit", 0) or 0 for g in target_guests) / len(target_guests)
    if _campaign_implies_departure_or_boundary(campaign_description):
        strategy, tone = "Guest relations — boundary notice", "Clear, respectful, and firm"
        key_message = "We are writing regarding your relationship with the property."
        cta = "If you have questions, reply to this message for documented follow-up."
    elif _campaign_implies_apology_or_recovery(campaign_description):
        strategy, tone = "Service recovery", "Empathetic and accountable"
        key_message = "We are sorry your experience missed the mark and want to make this right."
        cta = "Share a time to connect so we can address your concerns directly."
    elif avg_spend > 3000:
        strategy, tone = "VIP Win-back", "Exclusive & polished"
        key_message = "You are among our most valued guests."
        cta = "Let your concierge tailor your next stay."
    elif avg_days >= 120 and avg_spend >= 800:
        strategy, tone = "Long-lapse win-back", "Warm and personal"
        key_message = "It has been a while — we have been holding a place for your return."
        cta = "Your guest preferences are on file; let us plan your next stay."
    elif avg_spend > 1500:
        strategy, tone = "Re-engagement", "Warm & appreciative"
        key_message = "We would love to welcome you back."
        cta = "Reserve your next experience with us."
    else:
        strategy, tone = "Retention", "Friendly & inviting"
        key_message = "Memorable stays await you."
        cta = "Discover what is new on property."

    if vip_count > len(target_guests) * 0.5 and not strategy.startswith("Guest relations"):
        strategy = "Premium " + strategy

    return {
        "strategy": strategy,
        "tone": tone,
        "key_message": key_message,
        "call_to_action": cta,
        "avg_spend": avg_spend,
        "avg_days_since_visit": avg_days,
        "vip_percentage": (vip_count / len(target_guests)) * 100,
    }


def _fallback_subject(guest: Dict[str, Any], strategy: Dict[str, Any]) -> str:
    first = (guest.get("name") or "Guest").split()[0]
    opts = [
        f"A note for you, {first}",
        f"Your next stay, thoughtfully prepared",
        strategy.get("key_message", "We look forward to hosting you")[:50],
    ]
    return random.choice(opts)


def _fallback_body(guest: Dict[str, Any], strategy: Dict[str, Any]) -> str:
    name = guest.get("name") or "Valued guest"
    days = guest.get("last_visit", "some time")
    return (
        f"Dear {name},\n\n"
        f"It has been {days} days since we last had the pleasure of your visit.\n\n"
        f"{strategy.get('key_message', '')}\n\n"
        f"{strategy.get('call_to_action', '')}\n\n"
        f"With warm regards,\nThe Retain AI Concierge"
    )


@tool
def generate_email(
    guest: Dict[str, Any], campaign_description: str, strategy: Dict[str, Any]
) -> Dict[str, Any]:
    """Gemini generates subject/body JSON; no discount language."""

    def _safe(v: Any, default: str = "") -> str:
        if v is None or v == "" or v == "nan":
            return default
        try:
            if pd.isna(v):
                return default
        except TypeError:
            pass
        return str(v)

    profile = f"""Guest: {guest.get('name')}
Type: {guest.get('guest_type')}
Spend: {guest.get('total_spend')}
Days since visit: {guest.get('last_visit')}
Event: {_safe(guest.get('event'))}
Preferences: {_safe(guest.get('room_preference'))}, {_safe(guest.get('favorite_service'))}
Campaign: {campaign_description}
Strategy: {strategy.get('strategy')} | Tone: {strategy.get('tone')}
Rules: NO discounts, NO percentages off, NO price cuts. Luxury hotel voice. JSON only:
{{"subject":"...","body":"..."}}"""

    try:
        r = _invoke_with_fallback(profile)
        text = r.content if hasattr(r, "content") else str(r)
        parsed = extract_json_from_response(str(text))
        subj = parsed.get("subject") or _fallback_subject(guest, strategy)
        body = parsed.get("body") or _fallback_body(guest, strategy)
    except Exception as e:
        print(f"Gemini API error in generate_email: {e}")
        subj = _fallback_subject(guest, strategy)
        body = _fallback_body(guest, strategy)

    return {
        "subject": subj,
        "body": body,
        "email": guest.get("email"),
        "guest_id": guest.get("guest_id") or guest.get("id"),
        "guest_name": guest.get("name"),
    }


@tool
def send_campaign(emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Demo send — returns counts only."""
    return {"status": "success", "sent_count": len(emails), "sample_emails": emails[:3]}


tools = [
    extract_guest_filters,
    merge_with_manual_filters,
    filter_guests,
    decide_strategy,
    generate_email,
    send_campaign,
]
