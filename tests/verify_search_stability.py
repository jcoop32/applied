import asyncio
import os
import sys
# Ensure app is in path
sys.path.append(os.getcwd())

from app.agents.google_researcher import GoogleResearcherAgent

async def test_search_stability():
    try:
        with open(".env", "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k] = v
    except: pass

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not found in .env")
        return

    print("🧪 Starting Search Stability Test...")
    agent = GoogleResearcherAgent(api_key=api_key)
    
    # Dummy profile
    profile = {
        "raw_text": "Experienced Python Developer with FastAPI and React skills.",
        "location": "Remote"
    }
    
    print("running gather_leads with limit=1 (should trigger one batch)...")
    try:
        leads = await agent.gather_leads(profile, limit=1)
        print(f"✅ Gathered {len(leads)} leads.")
        for l in leads:
            print(f" - {l.get('title')} @ {l.get('company')} ({l.get('url')})")
            
    except Exception as e:
        print(f"❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_search_stability())
