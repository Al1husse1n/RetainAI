"""
Complaint resolution tools (LangChain @tool) backed by Ollama.
Generates and sends resolution emails for customer complaints.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from langchain_ollama import ChatOllama

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


# ----- tools -----

@tool
def generate_resolution_email(
    name: str, email: str, complaint_description: str
) -> Dict[str, Any]:
    """Generate a resolution email for the customer complaint using Ollama."""
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

Return ONLY the JSON object."""

    try:
        r = get_llm().invoke(prompt)
        content = r.content if hasattr(r, "content") else str(r)
        out = extract_json_from_response(str(content))
        subj = out.get("subject", f"Issue Resolution for {name}")
        body = out.get("body", f"Dear {name},\n\nWe have resolved your complaint regarding: {complaint_description}.\n\nThank you for bringing this to our attention.\n\nBest regards,\nThe Retain AI Team")
    except Exception:
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