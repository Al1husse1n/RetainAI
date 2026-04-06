"""
Complaint resolution tools (LangChain @tool) backed by Google Gemini.
Generates and sends resolution emails for customer complaints.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

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


# ----- tools -----

@tool
def generate_resolution_email(
    name: str, email: str, complaint_description: str
) -> Dict[str, Any]:
    """Generate a resolution email for the customer complaint using Google Gemini."""
    prompt = f"""Generate a professional resolution email for the following customer complaint.

Customer Name: {name}
Email: {email}
Complaint Description: {complaint_description}

Rules:
- Polite and professional tone
- Confirm that the issue has been resolved
- Apologize if appropriate
- No discounts, offers, or price cuts
- Keep it concise
- JSON only: {{"subject":"...","body":"..."}}
Return ONLY valid JSON.
Do NOT include markdown.
Do NOT include explanation.
Do NOT include ```json.
Output must start with curly brace and end with curly brace like json.
."""

    try:
        r = _invoke_with_fallback(prompt)
        content = r.content if hasattr(r, "content") else str(r)
        out = extract_json_from_response(str(content))
        subj = out.get("subject", f"Issue Resolution for {name}")
        body = out.get("body", f"Dear {name},\n\nWe have resolved your complaint regarding: {complaint_description}.\n\nThank you for bringing this to our attention.\n\nBest regards,\nThe Retain AI Team")
    except Exception as e:
        print(f"Gemini API error in generate_resolution_email: {e}")
        subj = f"Issue Resolution for {name}"
        body = f"Dear {name},\n\nWe apologize for any inconvenience caused by: {complaint_description}.\n\nThe issue has been resolved.\n\nBest regards,\nThe Retain AI Team"

    return {
        "subject": subj,
        "body": body,
        "email": email,
        "name": name,
    }


@tool
def send_resolution_email(email_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Demo send resolution email — returns success status."""
    return {
        "status": "success",
        "sent": 1,
        "email_details": {
            "to": email_dict.get("email"),
            "subject": email_dict.get("subject"),
            "body": email_dict.get("body"),
        }
    }


tools = [
    generate_resolution_email,
    send_resolution_email,
]