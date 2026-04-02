"""
Campaign pipeline tools (LangChain @tool) backed by Ollama.
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

import pandas as pd
from langchain_core.tools import tool
from langchain_ollama import ChatOllama

# --- Paths: demo_guests.csv lives in main/agents/ ---
_AGENTS_DIR = Path(__file__).resolve().parent
_DEMO_CSV = _AGENTS_DIR / "demo_guests.csv"

# Ollama: override via env for hackathon machines
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

_llm: Optional[ChatOllama] = None


def get_llm() -> ChatOllama:
    """Lazy-init so Django can import this module before Ollama is up."""
    global _llm
    if _llm is None:
        _llm = ChatOllama(
            model=OLLAMA_MODEL,
            temperature=0.3,
            base_url=OLLAMA_BASE_URL,
        )
    return _llm


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
- send_limit (int)
No markdown, JSON only."""

    try:
        r = get_llm().invoke(prompt)
        content = r.content if hasattr(r, "content") else str(r)
        out = extract_json_from_response(str(content))
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
        return out
    except Exception:
        return {}


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
    if f.get("send_limit"):
        df = df.sort_values(by="total_spend", ascending=False).head(int(f["send_limit"]))

    return df.to_dict(orient="records")


@tool
def decide_strategy(
    campaign_description: str, target_guests: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Pick strategy from cohort stats (fast path — no extra LLM round-trip)."""
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

    if avg_spend > 3000:
        strategy, tone = "VIP Win-back", "Exclusive & polished"
        key_message = "You are among our most valued guests."
        cta = "Let your concierge tailor your next stay."
    elif avg_spend > 1500:
        strategy, tone = "Re-engagement", "Warm & appreciative"
        key_message = "We would love to welcome you back."
        cta = "Reserve your next experience with us."
    else:
        strategy, tone = "Retention", "Friendly & inviting"
        key_message = "Memorable stays await you."
        cta = "Discover what is new on property."

    if vip_count > len(target_guests) * 0.5:
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
    """Ollama generates subject/body JSON; no discount language."""

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
        r = get_llm().invoke(profile)
        text = r.content if hasattr(r, "content") else str(r)
        parsed = extract_json_from_response(str(text))
        subj = parsed.get("subject") or _fallback_subject(guest, strategy)
        body = parsed.get("body") or _fallback_body(guest, strategy)
    except Exception:
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
