# agent.py
from dotenv import load_dotenv
load_dotenv()

from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import create_react_agent
from tools import tools, llm

system_prompt = """You are Retain AI - Luxury Hotel Campaign Assistant.

You help hotels create and send highly personalized email campaigns.

STRICT TOOL FLOW:
1. extract_guest_filters
2. merge_with_manual_filters
3. filter_guests
4. decide_strategy
5. generate_email (FOR EACH GUEST)
6. send_campaign

IMPORTANT RULES:
- ALWAYS use tools
- DO NOT skip steps
- generate_email MUST be called multiple times (once per guest)
- Final output MUST come from send_campaign

Tone: professional, warm, luxurious, exclusive.
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("placeholder", "{messages}")
])

agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=prompt,
)

def run_agent(user_input: str, manual_filters: dict = None):
    inputs = {
        "messages": [
            ("user", f"{user_input}\nManual filters: {manual_filters or {}}")
        ]
    }

    result = agent.invoke(inputs)
    return result

print("✅ Retain AI Agent ready (LangGraph)")