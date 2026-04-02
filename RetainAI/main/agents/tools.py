# tools.py
from langchain_core.tools import tool
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import pandas as pd
import json
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# ====================== LOAD DATA ======================

def load_guests():
    csv_path = "demo_guests.csv"
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)

    if "last_visit" in df.columns:
        df["last_visit"] = pd.to_datetime(df["last_visit"], errors="coerce")

    return df


# ====================== LLM ======================

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.3,
)

# ====================== SCHEMAS ======================

class GuestFilters(BaseModel):
    max_days_since_last_visit: Optional[int] = None
    min_days_since_last_visit: Optional[int] = None
    min_spend: Optional[float] = None
    max_spend: Optional[float] = None
    max_complaint_count: Optional[int] = None
    guest_types: Optional[List[str]] = None
    send_limit: Optional[int] = None


class StrategyOutput(BaseModel):
    strategy: str
    tone: str
    key_message: str
    call_to_action: str


class EmailOutput(BaseModel):
    subject: str
    body: str


# ====================== TOOLS ======================

@tool
def extract_guest_filters(campaign_description: str) -> Dict[str, Any]:
    """Extract filters from natural language."""
    prompt = f"""
Convert this into JSON:
{GuestFilters.model_json_schema()}

Today: {datetime.now().strftime("%Y-%m-%d")}
Request: {campaign_description}

Return ONLY JSON.
"""
    result = llm.with_structured_output(GuestFilters).invoke(prompt)
    return result.model_dump()


@tool
def merge_with_manual_filters(
    extracted_filters: Dict[str, Any],
    manual_filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge filters (manual overrides AI)."""
    merged = dict(extracted_filters or {})

    for k, v in (manual_filters or {}).items():
        if v is not None and str(v).strip() != "":
            merged[k] = v

    return merged


@tool
def filter_guests(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Filter dataset."""
    df = load_guests()

    if filters.get("max_days_since_last_visit"):
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=filters["max_days_since_last_visit"])
        df = df[df["last_visit"] >= cutoff]

    if filters.get("min_days_since_last_visit"):
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=filters["min_days_since_last_visit"])
        df = df[df["last_visit"] < cutoff]

    if filters.get("min_spend"):
        df = df[df["total_spend"] >= filters["min_spend"]]

    if filters.get("max_spend"):
        df = df[df["total_spend"] <= filters["max_spend"]]

    if filters.get("max_complaint_count"):
        df = df[df["complaint_count"] <= filters["max_complaint_count"]]

    if filters.get("guest_types"):
        df = df[df["guest_type"].isin(filters["guest_types"])]

    if filters.get("send_limit"):
        df = df.sort_values(by="total_spend", ascending=False).head(filters["send_limit"])

    return df.to_dict(orient="records")


@tool
def decide_strategy(campaign_description: str, target_guests: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Decide strategy."""
    prompt = f"""
Campaign: {campaign_description}
Guests count: {len(target_guests)}

Return JSON:
{StrategyOutput.model_json_schema()}
"""
    result = llm.with_structured_output(StrategyOutput).invoke(prompt)
    return result.model_dump()


@tool
def generate_email(
    guest: Dict[str, Any],
    campaign_description: str,
    strategy: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate email."""
    prompt = f"""
Guest: {json.dumps(guest)}
Strategy: {strategy}
Campaign: {campaign_description}

Return JSON:
{EmailOutput.model_json_schema()}
"""
    result = llm.with_structured_output(EmailOutput).invoke(prompt)
    email = result.model_dump()

    email.update({
        "email": guest.get("email"),
        "guest_id": guest.get("guest_id")
    })

    return email


@tool
def send_campaign(emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Send campaign."""
    return {
        "status": "success",
        "sent_count": len(emails),
        "sample_emails": emails[:3]
    }


tools = [
    extract_guest_filters,
    merge_with_manual_filters,
    filter_guests,
    decide_strategy,
    generate_email,
    send_campaign,
]

print("✅ Tools ready")