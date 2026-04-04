# agent2.py
from tools import tools, load_guests
import json
from datetime import datetime

# Create tools dictionary
tool_dict = {t.name: t for t in tools}

def run_agent(user_input: str, manual_filters: dict = None):
    """Run tools in sequence and show real-time progress"""
    
    print("\n" + "="*70)
    print("📋 STEP 1: Extracting filters from campaign description")
    print("="*70)
    
    extracted = tool_dict["extract_guest_filters"].invoke({
        "campaign_description": user_input
    })
    print(f"✅ Extracted filters: {json.dumps(extracted, indent=2)}")
    
    print("\n" + "="*70)
    print("📋 STEP 2: Merging with manual filters")
    print("="*70)
    
    merged = tool_dict["merge_with_manual_filters"].invoke({
        "extracted_filters": extracted,
        "manual_filters": manual_filters or {}
    })
    print(f"✅ Merged filters: {json.dumps(merged, indent=2)}")
    
    print("\n" + "="*70)
    print("📋 STEP 3: Filtering guests")
    print("="*70)
    
    filtered_guests = tool_dict["filter_guests"].invoke({
        "filters": merged
    })
    
    if not filtered_guests:
        print("\n❌ No guests match the specified filters")
        return {"status": "no_guests_found"}
    
    print("\n" + "="*70)
    print("📋 STEP 4: Deciding campaign strategy")
    print("="*70)
    
    strategy = tool_dict["decide_strategy"].invoke({
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
        
        email = tool_dict["generate_email"].invoke({
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
    
    result = tool_dict["send_campaign"].invoke({"emails": emails})
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