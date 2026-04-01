import requests
from dotenv import load_dotenv
import pandas as pd
import json
from langchain.agents import create_agent   
from langchain.tools import tool
from langchain.chat_models import init_chat_model

load_dotenv()

@tool('match_headers', description="match the headers with default filters(the key parts in the filter dictionary/json)")
def match_headers(filter: dict):
    df = pd.read_csv("guests.csv")
    headers = df.columns.tolist()

    model = init_chat_model(
        model = "gemini-2.5-flash",
        temperature = 0.3,
        model_kwargs={
            "response_mime_type": "application/json"  
        }
    )

    system_content = """
You are a data analyst that compares and filter out the headers in the csv that are similar in name or category to those given to you,
You will be given two things:
    1. A list of headers from a csv
    2. A dictionary containing categories and their values
Rules:
- Match headers based on semantic similarity (e.g., "email" matches "e-mail", "email_address")
- If a header matches multiple categories, choose the most relevant one
- If you don't find any match for a category, Include the category in the output, but the value of the key/category must be "none" in the json
- Output ONLY valid JSON, no other text

Example: if in the list it says "name" and in the dictionary it says "full_name": "ali", you output:-
Example output format:
{"full_name": "name"}
"""
    user_content = f"""
The headers in the csv are {headers}.
The categories you are going to match them with are {filter}.
"""
    response = model.invoke([
        {
            "role": "system",
            "content": system_content
        },

        {
            "role": "user",
            "content": user_content
        }
    ])

    try:
        result = json.loads(response.content)
        return result
    except json.JSONDecodeError as e:
        return f"Failed to parse LLM response as JSON: {e.msg}"


@tool("filter_guests", description="Apply user-selected filters on the guests.csv file using the header mapping")
def filter_guests(header_mapping: dict, user_filters: dict):
    """
    header_mapping: Output from match_headers tool (e.g. {"last_visit": "last_visit_date", "total_spend": "spend", ...})
    user_filters: Filters coming from frontend (e.g. {"last_visit": "0-30", "min_spend": "5000", ...})
    """
    try:
        df = pd.read_csv("guests.csv")
    except Exception as e:
        return {"error": f"Failed to load CSV: {str(e)}"}

    # Start with full dataframe
    filtered_df = df.copy()
    applied_filters = {}

    try:
        # Last Visit Filter
        if user_filters.get("last_visit") and header_mapping.get("last_visit"):
            col = header_mapping["last_visit"]
            days = user_filters["last_visit"]
            
            if days == "0-30":
                filtered_df = filtered_df[filtered_df[col] <= 30]
            elif days == "30-60":
                filtered_df = filtered_df[(filtered_df[col] > 30) & (filtered_df[col] <= 60)]
            elif days == "60-90":
                filtered_df = filtered_df[(filtered_df[col] > 60) & (filtered_df[col] <= 90)]
            elif days == "90+":
                filtered_df = filtered_df[filtered_df[col] > 90]
            applied_filters["last_visit"] = days

        # Min Spend Filter
        if user_filters.get("min_spend") and header_mapping.get("min_spend"):
            col = header_mapping["min_spend"]
            min_spend = float(user_filters["min_spend"])
            filtered_df = filtered_df[filtered_df[col] >= min_spend]
            applied_filters["min_spend"] = min_spend

        # Has Compliant Filter
        if user_filters.get("has_compliant") and header_mapping.get("has_compliant"):
            col = header_mapping["has_compliant"]
            val = user_filters["has_compliant"].lower()
            if val in ["yes", "true", "1"]:
                filtered_df = filtered_df[filtered_df[col].astype(str).str.lower().isin(["yes", "true", "1"])]
            elif val in ["no", "false", "0"]:
                filtered_df = filtered_df[filtered_df[col].astype(str).str.lower().isin(["no", "false", "0"])]
            applied_filters["has_compliant"] = val

        # Guest Type Filter
        if user_filters.get("guest_type") and header_mapping.get("guest_type"):
            col = header_mapping["guest_type"]
            gtype = user_filters["guest_type"]
            if gtype != "All":
                filtered_df = filtered_df[filtered_df[col].astype(str).str.contains(gtype, case=False)]
            applied_filters["guest_type"] = gtype

        # Campaign Type (if exists in data)
        if user_filters.get("campaign_type") and header_mapping.get("campaign_type"):
            col = header_mapping["campaign_type"]
            filtered_df = filtered_df[filtered_df[col].astype(str).str.contains(user_filters["campaign_type"], case=False)]
            applied_filters["campaign_type"] = user_filters["campaign_type"]

        # Send Limit / Max Email (usually not for filtering rows, but for later use)
        max_emails = user_filters.get("max_email")
        if max_emails:
            applied_filters["max_email"] = int(max_emails)

    except Exception as e:
        return {"error": f"Error applying filters: {str(e)}"}

    result = {
        "total_matched": len(filtered_df),
        "applied_filters": applied_filters,
        "rows": filtered_df.to_dict(orient="records") if not filtered_df.empty else [],
        "columns": list(filtered_df.columns)
    }

    return result

    

@tool('score_guests', description="return value score and return probability of the guests")
def score_guests():
    pass

@tool('decide_strategy', description="return strategy on how to approach the customer")
def decide_strategy():
    pass

@tool('generate_email', description="return generated email")
def generate_email():
    pass

@tool('send_campaign', description="send emails to customers")
def send_campaign():
    pass
