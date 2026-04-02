# tools2.py
from langchain_core.tools import tool
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import pandas as pd
import json
import os
import re
from langchain_ollama import ChatOllama

# ====================== LOAD DATA ======================

def load_guests():
    """Load guests CSV file"""
    csv_path = "demo_guests.csv"
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)
    
    # Convert last_visit to datetime (your CSV has days since last visit as integer)
    if "last_visit" in df.columns:
        # Your CSV has last_visit as number of days since last visit
        # Convert to actual date
        today = datetime.now()
        df["last_visit_date"] = df["last_visit"].apply(
            lambda x: today - timedelta(days=int(x)) if pd.notna(x) else None
        )
    
    print(f"✅ Loaded {len(df)} guests from CSV")
    print(f"   Columns: {list(df.columns)}")
    
    return df


# ====================== OLLAMA SETUP ======================

llm = ChatOllama(
    model="llama3.2:3b",
    temperature=0.3,
    base_url="http://localhost:11434",
)


def extract_json_from_response(response_text: str) -> dict:
    """Extract JSON from LLM response"""
    try:
        response_text = response_text.strip()
        
        # Remove markdown code blocks
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        # Find JSON object
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        return json.loads(response_text)
    except Exception as e:
        print(f"⚠️ JSON parsing warning: {e}")
        return {}


# ====================== TOOLS ======================

@tool
def extract_guest_filters(campaign_description: str) -> Dict[str, Any]:
    """Extract filters from natural language campaign description"""
    
    prompt = f"""Today's date: {datetime.now().strftime("%Y-%m-%d")}

Campaign: {campaign_description}

Extract filters as JSON. Use these exact key names:
{{
    "min_days_since_last_visit": number or null (minimum days since last visit - guests who haven't visited for at least this many days),
    "max_days_since_last_visit": number or null (maximum days since last visit),
    "min_spend": number or null (minimum total_spend in dollars),
    "max_spend": number or null (maximum total_spend in dollars),
    "guest_types": list of strings or null (VIP, Regular, etc. - based on guest_type column),
    "had_complaint": boolean or null (True/False),
    "send_limit": number or null (maximum number of guests to target)
}}

Examples:
- "haven't visited in over 12 months" means min_days_since_last_visit = 365
- "spent more than $1500" means min_spend = 1500
- "VIP guests" means guest_types = ["VIP"]
- "Limit to 10 guests" means send_limit = 10

Return ONLY valid JSON, no other text."""
    
    try:
        response = llm.invoke(prompt)
        result = extract_json_from_response(response.content)
        
        # Ensure numeric values are proper numbers
        for key in ['min_days_since_last_visit', 'max_days_since_last_visit', 'min_spend', 'max_spend', 'send_limit']:
            if key in result and result[key] is not None:
                try:
                    result[key] = float(result[key]) if 'spend' in key else int(result[key])
                except:
                    pass
        
        return result
    except Exception as e:
        print(f"Error in extract_guest_filters: {e}")
        # Fallback to manual extraction
        filters = {}
        if "12 months" in campaign_description or "365" in campaign_description:
            filters['min_days_since_last_visit'] = 365
        if "$1500" in campaign_description or "1500" in campaign_description:
            filters['min_spend'] = 1500
        if "Limit to 10" in campaign_description or "10 guests" in campaign_description:
            filters['send_limit'] = 10
        return filters


@tool
def merge_with_manual_filters(
    extracted_filters: Dict[str, Any],
    manual_filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge AI-extracted filters with manual overrides"""
    merged = dict(extracted_filters or {})
    for k, v in (manual_filters or {}).items():
        if v is not None and str(v).strip() != "":
            merged[k] = v
    return merged


@tool
def filter_guests(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Filter guests based on criteria"""
    df = load_guests()
    original_count = len(df)
    
    print(f"\n📊 Applying filters:")
    
    # Track applied filters
    applied_filters = []
    
    # Filter by days since last visit (using the integer column directly)
    if filters.get("min_days_since_last_visit"):
        before = len(df)
        df = df[df["last_visit"] >= filters["min_days_since_last_visit"]]
        after = len(df)
        applied_filters.append(f"   • Last visit ≥ {filters['min_days_since_last_visit']} days ago: {before} → {after}")
    
    if filters.get("max_days_since_last_visit"):
        before = len(df)
        df = df[df["last_visit"] <= filters["max_days_since_last_visit"]]
        after = len(df)
        applied_filters.append(f"   • Last visit ≤ {filters['max_days_since_last_visit']} days ago: {before} → {after}")
    
    # Filter by spend
    if filters.get("min_spend"):
        before = len(df)
        df = df[df["total_spend"] >= filters["min_spend"]]
        after = len(df)
        applied_filters.append(f"   • Spend ≥ ${filters['min_spend']}: {before} → {after}")
    
    if filters.get("max_spend"):
        before = len(df)
        df = df[df["total_spend"] <= filters["max_spend"]]
        after = len(df)
        applied_filters.append(f"   • Spend ≤ ${filters['max_spend']}: {before} → {after}")
    
    # Filter by guest type (if column exists)
    if filters.get("guest_types") and "guest_type" in df.columns:
        before = len(df)
        df = df[df["guest_type"].isin(filters["guest_types"])]
        after = len(df)
        applied_filters.append(f"   • Guest type in {filters['guest_types']}: {before} → {after}")
    
    # Filter by complaint status
    if filters.get("had_complaint") is not None and "had_complaint" in df.columns:
        before = len(df)
        df = df[df["had_complaint"] == filters["had_complaint"]]
        after = len(df)
        applied_filters.append(f"   • Had complaint = {filters['had_complaint']}: {before} → {after}")
    
    for filter_line in applied_filters:
        print(filter_line)
    
    # Apply send limit
    if filters.get("send_limit"):
        before = len(df)
        df = df.sort_values(by="total_spend", ascending=False).head(filters["send_limit"])
        after = len(df)
        applied_filters.append(f"   • Send limit ({filters['send_limit']}): {before} → {after}")
        print(f"   • Send limit ({filters['send_limit']}): {before} → {after}")
    
    print(f"\n✅ Final: {original_count} → {len(df)} guests")
    return df.to_dict(orient="records")


@tool
def decide_strategy(campaign_description: str, target_guests: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Decide campaign strategy based on guest data"""
    
    if not target_guests:
        return {"strategy": "No guests", "tone": "N/A", "key_message": "N/A", "call_to_action": "N/A"}
    
    # Calculate metrics
    avg_spend = sum(g.get("total_spend", 0) for g in target_guests) / len(target_guests)
    vip_count = sum(1 for g in target_guests if g.get("guest_type") == "VIP")
    avg_days = sum(g.get("last_visit", 0) for g in target_guests) / len(target_guests)
    
    # Strategy logic based on data
    if avg_spend > 3000:
        strategy = "VIP Win-back"
        tone = "Exclusive & Luxurious"
        key_message = "You're one of our most valued guests"
        call_to_action = "Claim your exclusive offer"
    elif avg_spend > 1500:
        strategy = "Re-engagement"
        tone = "Warm & Appreciative"
        key_message = "We miss having you with us"
        call_to_action = "Book your return stay"
    else:
        strategy = "Retention"
        tone = "Friendly & Inviting"
        key_message = "Great experiences await you"
        call_to_action = "Discover our special rates"
    
    # Add personalization based on guest composition
    if vip_count > len(target_guests) * 0.5:
        strategy = "Premium " + strategy
        tone = "Ultra-premium " + tone
    
    return {
        "strategy": strategy,
        "tone": tone,
        "key_message": key_message,
        "call_to_action": call_to_action,
        "avg_spend": avg_spend,
        "avg_days_since_visit": avg_days,
        "vip_percentage": (vip_count / len(target_guests)) * 100
    }


# tools2.py
from langchain_core.tools import tool
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import pandas as pd
import json
import os
import re
import random
from langchain_ollama import ChatOllama

# ====================== LOAD DATA ======================

def load_guests():
    """Load guests CSV file"""
    csv_path = "demo_guests.csv"
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)
    
    # Convert last_visit to datetime (your CSV has days since last visit as integer)
    if "last_visit" in df.columns:
        # Your CSV has last_visit as number of days since last visit
        # Convert to actual date
        today = datetime.now()
        df["last_visit_date"] = df["last_visit"].apply(
            lambda x: today - timedelta(days=int(x)) if pd.notna(x) else None
        )
    
    print(f"✅ Loaded {len(df)} guests from CSV")
    print(f"   Columns: {list(df.columns)}")
    
    return df


# ====================== OLLAMA SETUP ======================

llm = ChatOllama(
    model="llama3.2:3b",
    temperature=0.3,
    base_url="http://localhost:11434",
)


def extract_json_from_response(response_text: str) -> dict:
    """Extract JSON from LLM response"""
    try:
        response_text = response_text.strip()
        
        # Remove markdown code blocks
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        # Find JSON object
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        return json.loads(response_text)
    except Exception as e:
        print(f"⚠️ JSON parsing warning: {e}")
        return {}


# ====================== TOOLS ======================

@tool
def extract_guest_filters(campaign_description: str) -> Dict[str, Any]:
    """Extract filters from natural language campaign description"""
    
    prompt = f"""Today's date: {datetime.now().strftime("%Y-%m-%d")}

Campaign: {campaign_description}

Extract filters as JSON. Use these exact key names:
{{
    "min_days_since_last_visit": number or null (minimum days since last visit - guests who haven't visited for at least this many days),
    "max_days_since_last_visit": number or null (maximum days since last visit),
    "min_spend": number or null (minimum total_spend in dollars),
    "max_spend": number or null (maximum total_spend in dollars),
    "guest_types": list of strings or null (VIP, Regular, etc. - based on guest_type column),
    "had_complaint": boolean or null (True/False),
    "send_limit": number or null (maximum number of guests to target)
}}

Examples:
- "haven't visited in over 12 months" means min_days_since_last_visit = 365
- "spent more than $1500" means min_spend = 1500
- "VIP guests" means guest_types = ["VIP"]
- "Limit to 10 guests" means send_limit = 10

Return ONLY valid JSON, no other text."""
    
    try:
        response = llm.invoke(prompt)
        result = extract_json_from_response(response.content)
        
        # Ensure numeric values are proper numbers
        for key in ['min_days_since_last_visit', 'max_days_since_last_visit', 'min_spend', 'max_spend', 'send_limit']:
            if key in result and result[key] is not None:
                try:
                    result[key] = float(result[key]) if 'spend' in key else int(result[key])
                except:
                    pass
        
        return result
    except Exception as e:
        print(f"Error in extract_guest_filters: {e}")
        # Fallback to manual extraction
        filters = {}
        if "12 months" in campaign_description or "365" in campaign_description:
            filters['min_days_since_last_visit'] = 365
        if "$1500" in campaign_description or "1500" in campaign_description:
            filters['min_spend'] = 1500
        if "Limit to 10" in campaign_description or "10 guests" in campaign_description:
            filters['send_limit'] = 10
        return filters


@tool
def merge_with_manual_filters(
    extracted_filters: Dict[str, Any],
    manual_filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge AI-extracted filters with manual overrides"""
    merged = dict(extracted_filters or {})
    for k, v in (manual_filters or {}).items():
        if v is not None and str(v).strip() != "":
            merged[k] = v
    return merged


@tool
def filter_guests(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Filter guests based on criteria"""
    df = load_guests()
    original_count = len(df)
    
    print(f"\n📊 Applying filters:")
    
    # Track applied filters
    applied_filters = []
    
    # Filter by days since last visit (using the integer column directly)
    if filters.get("min_days_since_last_visit"):
        before = len(df)
        df = df[df["last_visit"] >= filters["min_days_since_last_visit"]]
        after = len(df)
        applied_filters.append(f"   • Last visit ≥ {filters['min_days_since_last_visit']} days ago: {before} → {after}")
    
    if filters.get("max_days_since_last_visit"):
        before = len(df)
        df = df[df["last_visit"] <= filters["max_days_since_last_visit"]]
        after = len(df)
        applied_filters.append(f"   • Last visit ≤ {filters['max_days_since_last_visit']} days ago: {before} → {after}")
    
    # Filter by spend
    if filters.get("min_spend"):
        before = len(df)
        df = df[df["total_spend"] >= filters["min_spend"]]
        after = len(df)
        applied_filters.append(f"   • Spend ≥ ${filters['min_spend']}: {before} → {after}")
    
    if filters.get("max_spend"):
        before = len(df)
        df = df[df["total_spend"] <= filters["max_spend"]]
        after = len(df)
        applied_filters.append(f"   • Spend ≤ ${filters['max_spend']}: {before} → {after}")
    
    # Filter by guest type (if column exists)
    if filters.get("guest_types") and "guest_type" in df.columns:
        before = len(df)
        df = df[df["guest_type"].isin(filters["guest_types"])]
        after = len(df)
        applied_filters.append(f"   • Guest type in {filters['guest_types']}: {before} → {after}")
    
    # Filter by complaint status
    if filters.get("had_complaint") is not None and "had_complaint" in df.columns:
        before = len(df)
        df = df[df["had_complaint"] == filters["had_complaint"]]
        after = len(df)
        applied_filters.append(f"   • Had complaint = {filters['had_complaint']}: {before} → {after}")
    
    for filter_line in applied_filters:
        print(filter_line)
    
    # Apply send limit
    if filters.get("send_limit"):
        before = len(df)
        df = df.sort_values(by="total_spend", ascending=False).head(filters["send_limit"])
        after = len(df)
        print(f"   • Send limit ({filters['send_limit']}): {before} → {after}")
    
    print(f"\n✅ Final: {original_count} → {len(df)} guests")
    return df.to_dict(orient="records")


@tool
def decide_strategy(campaign_description: str, target_guests: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Decide campaign strategy based on guest data"""
    
    if not target_guests:
        return {"strategy": "No guests", "tone": "N/A", "key_message": "N/A", "call_to_action": "N/A"}
    
    # Calculate metrics
    avg_spend = sum(g.get("total_spend", 0) for g in target_guests) / len(target_guests)
    vip_count = sum(1 for g in target_guests if g.get("guest_type") == "VIP")
    avg_days = sum(g.get("last_visit", 0) for g in target_guests) / len(target_guests)
    
    # Strategy logic based on data
    if avg_spend > 3000:
        strategy = "VIP Win-back"
        tone = "Exclusive & Luxurious"
        key_message = "You're one of our most valued guests"
        call_to_action = "Claim your exclusive experience"
    elif avg_spend > 1500:
        strategy = "Re-engagement"
        tone = "Warm & Appreciative"
        key_message = "We miss having you with us"
        call_to_action = "Book your return stay"
    else:
        strategy = "Retention"
        tone = "Friendly & Inviting"
        key_message = "Great experiences await you"
        call_to_action = "Discover our offerings"
    
    # Add personalization based on guest composition
    if vip_count > len(target_guests) * 0.5:
        strategy = "Premium " + strategy
        tone = "Ultra-premium " + tone
    
    return {
        "strategy": strategy,
        "tone": tone,
        "key_message": key_message,
        "call_to_action": call_to_action,
        "avg_spend": avg_spend,
        "avg_days_since_visit": avg_days,
        "vip_percentage": (vip_count / len(target_guests)) * 100
    }


def generate_fallback_subject(guest: Dict[str, Any], strategy: Dict[str, Any]) -> str:
    """Generate fallback subject line without discounts"""
    name = guest.get('name', 'Valued Guest').split()[0]
    guest_type = guest.get('guest_type', 'Regular')
    
    if guest_type == 'VIP':
        subjects = [
            f"An Exclusive Experience Awaits You, {name}",
            f"Your VIP Access to Luxury",
            f"Personalized Luxury Just for You, {name}"
        ]
    else:
        subjects = [
            f"We've Prepared Something Special for You, {name}",
            f"Your Next Experience Awaits",
            f"Rediscover the Art of Hospitality, {name}"
        ]
    
    return random.choice(subjects)


def generate_fallback_email(guest: Dict[str, Any], strategy: Dict[str, Any]) -> str:
    """Generate fallback email body without discounts"""
    name = guest.get('name', 'Valued Guest')
    guest_type = guest.get('guest_type', 'Regular')
    spend = guest.get('total_spend', 0)
    days_ago = guest.get('last_visit', 0)
    favorite_service = guest.get('favorite_service', '')
    room_preference = guest.get('room_preference', '')
    had_complaint = guest.get('had_complaint', False)
    event = guest.get('event', '')
    
    # Build personalized greeting
    if guest_type == 'VIP':
        greeting = f"Dear {name}, our esteemed VIP guest"
    else:
        greeting = f"Dear {name}"
    
    # Acknowledge past visits
    visit_acknowledgment = f"It's been {days_ago} days since your last stay with us."
    if event and event != 'nan':
        visit_acknowledgment += f" We fondly remember celebrating your {event} with you."
    
    # Mention preferences
    preference_line = ""
    if room_preference and room_preference != 'nan':
        preference_line += f" Your preferred {room_preference} accommodations are always held to the highest standard. "
    if favorite_service and favorite_service != 'nan':
        preference_line += f"Our {favorite_service} team looks forward to welcoming you back. "
    
    # Complaint acknowledgment (without compensation)
    complaint_line = ""
    if had_complaint:
        complaint_line = "We've taken your feedback to heart and have enhanced our services to ensure every moment of your stay is flawless. "
    
    # Spend acknowledgment
    spend_line = f"As someone who has experienced ${spend:,.0f} in unforgettable moments, you understand the difference true luxury makes."
    
    # Main message
    main_message = strategy.get('key_message', 'We look forward to welcoming you back')
    cta = strategy.get('call_to_action', 'Contact your personal concierge')
    
    body = f"""{greeting},

{visit_acknowledgment}

{complaint_line}{preference_line}{spend_line}

{main_message}. {cta} to begin planning your return.

Our team is ready to craft an experience tailored specifically to your preferences.

Warm regards,
Kuriftu Hotel Team
"""
    
    return body


@tool
def generate_email(guest: Dict[str, Any], campaign_description: str, strategy: Dict[str, Any]) -> Dict[str, Any]:
    """Generate personalized email using LLM based on guest data - NO DISCOUNTS"""
    
    # Helper function to handle NaN values
    def safe_get(value, default='Not specified'):
        if pd.isna(value) or value == 'nan' or value == '':
            return default
        return value
    
    # Build a rich guest profile
    guest_profile = f"""
GUEST INFORMATION:
- Name: {guest.get('name', 'Valued Guest')}
- Guest Type: {safe_get(guest.get('guest_type'), 'Regular')}
- Total Lifetime Spend: ${guest.get('total_spend', 0):,.2f}
- Days Since Last Visit: {guest.get('last_visit', 0)} days
- Number of Previous Visits: {guest.get('visit_count', 0)} visits
- Special Event Celebrated: {safe_get(guest.get('event'))}
- Room Preference: {safe_get(guest.get('room_preference'))}
- Favorite Service: {safe_get(guest.get('favorite_service'))}
- Had Previous Complaint: {'Yes' if guest.get('had_complaint') else 'No'}
- Complaint Type (if any): {safe_get(guest.get('complaint_type'), 'None')}
- Cancellation Count: {guest.get('cancellation_count', 0)}
- Country of Origin: {safe_get(guest.get('country'))}
"""

    # Campaign context
    campaign_context = f"""
CAMPAIGN CONTEXT:
- Campaign Goal: {campaign_description}
- Strategy Type: {strategy.get('strategy', 'Re-engagement')}
- Recommended Tone: {strategy.get('tone', 'Warm and exclusive')}
- Key Message: {strategy.get('key_message', 'We value your presence')}
- Call to Action: {strategy.get('call_to_action', 'Book your next experience')}
"""

    # Email generation prompt
    prompt = f"""{guest_profile}

{campaign_context}

TASK: Write a personalized, luxurious email to this guest.

IMPORTANT RULES:
1. **NO DISCOUNTS, NO PRICE REDUCTIONS, NO PERCENTAGE OFF** - Never mention any form of discount
2. Focus on: exclusive experiences, personalized service, luxury amenities, unique offerings
3. Reference their specific preferences (room type, favorite service, past celebrations)
4. If they had a complaint, acknowledge it and show improvement without offering compensation
5. If they're a VIP guest, emphasize exclusive access and premium treatment
6. The tone should be {strategy.get('tone', 'Warm and exclusive')}
7. Keep the email concise (150-250 words)
8. Do not mention any specific prices or cost savings

OUTPUT FORMAT (JSON only):
{{
    "subject": "Email subject line (max 60 chars, no discount language)",
    "body": "Full email body - warm, personalized, no discounts"
}}

Return ONLY valid JSON, no other text."""

    try:
        response = llm.invoke(prompt)
        result = extract_json_from_response(response.content)
        
        email = {
            "subject": result.get("subject", generate_fallback_subject(guest, strategy)),
            "body": result.get("body", generate_fallback_email(guest, strategy)),
            "email": guest.get("email"),
            "guest_id": guest.get("id"),
            "guest_name": guest.get("name", "Valued Guest")
        }
        
        return email
        
    except Exception as e:
        print(f"⚠️ LLM email generation failed for {guest.get('name', 'Guest')}: {e}")
        # Fallback to template-based email (still no discounts)
        return {
            "subject": generate_fallback_subject(guest, strategy),
            "body": generate_fallback_email(guest, strategy),
            "email": guest.get("email"),
            "guest_id": guest.get("id"),
            "guest_name": guest.get("name", "Valued Guest")
        }


@tool
def send_campaign(emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Send email campaign"""
    return {
        "status": "success",
        "sent_count": len(emails),
        "message": f"Successfully sent {len(emails)} emails"
    }


# List of all available tools
tools = [
    extract_guest_filters,
    merge_with_manual_filters,
    filter_guests,
    decide_strategy,
    generate_email,
    send_campaign,
]

print("✅ Tools ready with Ollama (llama3.2:3b)")
print(f"📧 Loaded {len(tools)} tools")
print("💡 Email generation uses LLM - NO discounts included")


@tool
def send_campaign(emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Send email campaign"""
    return {
        "status": "success",
        "sent_count": len(emails),
        "message": f"Successfully sent {len(emails)} emails"
    }


tools = [
    extract_guest_filters,
    merge_with_manual_filters,
    filter_guests,
    decide_strategy,
    generate_email,
    send_campaign,
]

print("✅ Tools ready with Ollama (llama3.2:3b)")
print(f"📧 Loaded {len(tools)} tools")