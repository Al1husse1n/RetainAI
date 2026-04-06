# compliant_agent.py
from .complaint_tools import (
    tools,
    generate_resolution_email,
    send_resolution_email,
)
import json
import traceback
from datetime import datetime

# Create tools dictionary
tool_dict = {t.name: t for t in tools}

def run_agent(name: str, email: str, complaint_description: str):
    """Run tools in sequence to resolve complaint and send email"""
    print("[CompliantAgent] Starting complaint resolution flow")
    print(f"[CompliantAgent] Inputs: name={name}, email={email}")
    print(f"[CompliantAgent] Complaint description length: {len(complaint_description or '')}")
    
    print("\n" + "="*70)
    print("📋 STEP 1: Generating resolution email")
    print("="*70)
    try:
        email_data = generate_resolution_email(name, email, complaint_description)
        print(f"✅ Generated email for: {email_data.get('name')}")
        print(f"   Subject: {email_data.get('subject')}")
        print(f"   Body preview: {email_data.get('body')[:100]}...")
    except Exception as exc:
        print(f"[CompliantAgent] Error generating resolution email: {exc}")
        traceback.print_exc()
        return {
            "status": "error",
            "error": "generate_resolution_email_failed",
            "details": str(exc)
        }
    
    print("\n" + "="*70)
    print("📋 STEP 2: Sending resolution email")
    print("="*70)
    try:
        send_result = send_resolution_email(email_data)
        print(f"✅ Email sent: {send_result.get('status')}")
    except Exception as exc:
        print(f"[CompliantAgent] Error sending resolution email: {exc}")
        traceback.print_exc()
        return {
            "status": "error",
            "error": "send_resolution_email_failed",
            "details": str(exc)
        }
    
    return {
        "status": "success",
        "email_sent": send_result,
        "email_data": email_data
    }


def run_agent_detailed(name: str, email: str, complaint_description: str):
    """Run agent and display detailed summary"""
    result = run_agent(name, email, complaint_description)
    
    if result.get("status") != "success":
        print("\n⚠️ Complaint resolution failed")
        print(f"[CompliantAgent] Result: {result}")
        return result
    
    print("\n" + "🎉"*35)
    print("COMPLAINT RESOLUTION COMPLETE!")
    print("🎉"*35)
    
    print(f"\n📊 FINAL SUMMARY:")
    print(f"   • Customer: {result['email_data']['name']}")
    print(f"   • Email: {result['email_data']['email']}")
    print(f"   • Status: {result['email_sent']['status']}")
    
    # Save to file
    output_file = f"complaint_resolution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    serializable_result = {
        "status": result["status"],
        "customer_name": result["email_data"]["name"],
        "customer_email": result["email_data"]["email"],
        "complaint_description": complaint_description,
        "email_subject": result["email_data"]["subject"],
        "email_body": result["email_data"]["body"],
        "send_status": result["email_sent"]["status"]
    }
    
    with open(output_file, "w") as f:
        json.dump(serializable_result, f, indent=2)
    print(f"\n💾 Full results saved to: {output_file}")
    return result


print("✅ Retain AI Complaint Resolution Agent ready (Sequential Executor)")
print("📧 Using Google Gemini API")
print("💡 Resolution emails will be generated and 'sent' as demo\n")