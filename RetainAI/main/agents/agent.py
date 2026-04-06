# agent2.py
from tools import tools, load_guests
import json
import traceback
from datetime import datetime

# Create tools dictionary
tool_dict = {t.name: t for t in tools}

def _invoke_tool(name: str, kwargs: dict):
    print(f"[Agent] Invoking tool: {name} with args: {json.dumps(kwargs, default=str)}")
    try:
        result = tool_dict[name].invoke(kwargs)
        print(f"[Agent] Tool {name} result: {json.dumps(result, default=str)[:400]}")
        return result
    except Exception as exc:
        print(f"[Agent] Error in tool {name}: {exc}")
        traceback.print_exc()
        raise


def run_agent(user_input: str, manual_filters: dict = None):
    """Run tools in sequence and show real-time progress"""
    
    print("\n" + "="*70)
    print("📋 STEP 1: Extracting filters from campaign description")
    print("="*70)
    
    extracted = _invoke_tool("extract_guest_filters", {
        "campaign_description": user_input
    })
    print(f"✅ Extracted filters: {json.dumps(extracted, indent=2)}")
    
    print("\n" + "="*70)
    print("📋 STEP 2: Merging with manual filters")
    print("="*70)
    
    merged = _invoke_tool("merge_with_manual_filters", {
        "extracted_filters": extracted,
        "manual_filters": manual_filters or {}
    })
    print(f"✅ Merged filters: {json.dumps(merged, indent=2)}")
    
    print("\n" + "="*70)
    print("📋 STEP 3: Filtering guests")
    print("="*70)
    
    filtered_guests = _invoke_tool("filter_guests", {
        "filters": merged
    })
    
    if not filtered_guests:
        print("\n❌ No guests match the specified filters")
        return {"status": "no_guests_found"}
    
    print("\n" + "="*70)
    print("📋 STEP 4: Deciding campaign strategy")
    print("="*70)
    
    strategy = _invoke_tool("decide_strategy", {
        "campaign_description": user_input,
        "target_guests": filtered_guests
    })
    print(f"✅ Strategy: {strategy.get('strategy')}")
    print(f"   Tone: {strategy.get('tone')}")
    print(f"   Message: {strategy.get('key_message')}")
    print(f"   CTA: {strategy.get('call_to_action')}")
    if strategy.get('avg_spend'):
        print(f"   Avg Spend: ${strategy.get('avg_spend', 0):.2f}")
        print(f"   Avg Days Since Visit: {strategy.get('avg_days_since_visit', 0):.0f}")
        print(f"   VIP %: {strategy.get('vip_percentage', 0):.0f}%")
    
    print("\n" + "="*70)
    print(f"📋 STEP 5: Generating personalized emails for {len(filtered_guests)} guests")
    print("="*70 + "\n")
    
    emails = []
    for i, guest in enumerate(filtered_guests, 1):
        print(f"{'─'*70}")
        print(f"📧 Email {i}/{len(filtered_guests)} for: {guest.get('name', 'Guest')}")
        print(f"{'─'*70}")
        
        email = _invoke_tool("generate_email", {
            "guest": guest,
            "campaign_description": user_input,
            "strategy": strategy
        })
        
        # Display email content
        print(f"📨 To: {email.get('email')}")
        print(f"📌 Subject: {email.get('subject')}")
        print(f"📝 Body:")
        print(f"{'─'*50}")
        print(email.get('body', ''))
        print(f"{'─'*50}\n")
        
        emails.append(email)
    
    print("\n" + "="*70)
    print("📋 STEP 6: Sending campaign")
    print("="*70)
    
    result = _invoke_tool("send_campaign", {"emails": emails})
    print(f"\n✅ {result.get('message')}")
    
    return {
        "status": "success",
        "guests_targeted": len(filtered_guests),
        "emails_sent": len(emails),
        "strategy": strategy,
        "filters_used": merged,
        "all_emails": emails
    }


def run_agent_detailed(user_input: str, manual_filters: dict = None):
    """Run agent and display summary"""
    result = run_agent(user_input, manual_filters)
    
    print("\n" + "🎉"*35)
    print("CAMPAIGN COMPLETE!")
    print("🎉"*35)
    
    if result.get("status") == "success":
        print(f"\n📊 FINAL SUMMARY:")
        print(f"   • Guests targeted: {result['guests_targeted']}")
        print(f"   • Emails generated: {result['emails_sent']}")
        print(f"   • Strategy used: {result['strategy']['strategy']}")
        print(f"   • Email tone: {result['strategy']['tone']}")
        
        # Save to file
        output_file = f"campaign_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Prepare serializable result
        serializable_emails = []
        for email in result['all_emails']:
            serializable_emails.append({
                "to": email.get("email"),
                "subject": email.get("subject"),
                "body": email.get("body"),
                "guest_name": email.get("guest_name")
            })
        
        serializable_result = {
            "status": result["status"],
            "guests_targeted": result["guests_targeted"],
            "emails_sent": result["emails_sent"],
            "strategy": result["strategy"],
            "filters_used": result["filters_used"],
            "generated_emails": serializable_emails
        }
        
        with open(output_file, "w") as f:
            json.dump(serializable_result, f, indent=2)
        print(f"\n💾 Full results saved to: {output_file}")
    
    return result


print("✅ Retain AI Agent ready (Sequential Executor)")
print("📧 Using Google Gemini API")
print("💡 Emails will be displayed as they're generated\n")