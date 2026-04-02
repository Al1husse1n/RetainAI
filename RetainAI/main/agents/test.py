# test.py
from agent import run_agent
import json

def test_campaign():
    user_input = """
    Create a reactivation campaign for guests who haven't visited in over 12 months 
    but have spent more than $1500. Limit to 10 guests.
    """

    print("🚀 Running Campaign...\n")

    result = run_agent(user_input)

    print("\n📊 RAW RESULT:")
    print("="*60)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    test_campaign()