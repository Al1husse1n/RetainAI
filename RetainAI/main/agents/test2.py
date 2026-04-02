# test2.py
from agent2 import run_agent_detailed
from tools2 import load_guests
import pandas as pd

def analyze_data():
    """Analyze the CSV data to understand what filtering will do"""
    df = pd.read_csv("demo_guests.csv")
    
    print("\n" + "📊"*30)
    print("DATA ANALYSIS")
    print("📊"*30)
    
    print(f"\nTotal guests: {len(df)}")
    print(f"\nLast visit distribution:")
    print(f"  • >365 days ago: {len(df[df['last_visit'] > 365])} guests")
    print(f"  • 180-365 days ago: {len(df[(df['last_visit'] >= 180) & (df['last_visit'] <= 365)])} guests")
    print(f"  • <180 days ago: {len(df[df['last_visit'] < 180])} guests")
    
    print(f"\nSpend distribution:")
    print(f"  • >$1500: {len(df[df['total_spend'] > 1500])} guests")
    print(f"  • $1000-$1500: {len(df[(df['total_spend'] >= 1000) & (df['total_spend'] <= 1500)])} guests")
    print(f"  • <$1000: {len(df[df['total_spend'] < 1000])} guests")
    
    print(f"\nGuests matching both conditions (visit >365 AND spend >1500):")
    matching = df[(df['last_visit'] > 365) & (df['total_spend'] > 1500)]
    print(f"  • Count: {len(matching)} guests")
    if len(matching) > 0:
        print(f"  • Names: {', '.join(matching['name'].head(5).tolist())}...")

def test_campaign():
    """Test the campaign agent with a sample request"""
    
    print("\n" + "🎯"*30)
    print("RETAIN AI - CAMPAIGN TEST")
    print("🎯"*30 + "\n")
    
    # First analyze the data
    analyze_data()
    
    user_input = """
    Find guests who visited recently (last 30–60 days) and send a limited-time offer to encourage immediate rebooking within the next 7 days.
    """
    
    print("\n" + "📝"*30)
    print("CAMPAIGN DESCRIPTION")
    print("📝"*30)
    print(user_input)
    
    print("\n🔄 Running campaign generation...\n")
    
    try:
        result = run_agent_detailed(user_input)
        
        if result.get("status") == "no_guests_found":
            print("\n⚠️ No guests matched the criteria. Try adjusting the filters.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_campaign()