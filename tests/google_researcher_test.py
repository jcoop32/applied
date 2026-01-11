import asyncio
import os
import json
from dotenv import load_dotenv
from app.agents.google_researcher import GoogleResearcherAgent

# Mock Profile
PROFILE = {
    "full_name": "Test User",
    "location": "San Francisco, CA",
    "skills": ["Python", "React", "AWS"],
    "experience": [],
    "raw_text": "Experienced Python Software Engineer looking for backend roles."
}

async def main():
    load_dotenv()
    
    # 1. Setup
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not found.")
        return

    # 2. Initialize Agent
    agent = GoogleResearcherAgent(api_key=api_key)
    print(f"🚀 Google Research started for: {PROFILE.get('full_name')}")

    # 3. Strategy
    print("--- Strategy ---")
    queries = await agent.generate_strategy(PROFILE)
    print(json.dumps(queries, indent=2))

    # 4. Gather Leads
    # We use a specific job title to force a single query path for debugging
    print("\n--- Live Search ---")
    leads = await agent.gather_leads(
        PROFILE, 
        limit=5, 
        job_title="Senior Software Engineer" 
    )

    # 5. Display Results
    print(f"\n✅ Result: Found {len(leads)} leads")
    for i, job in enumerate(leads, 1):
        print(f"{i}. {job.get('title')} @ {job.get('company')}")
        print(f"   URL: {job.get('url')}")
        print("-" * 30)

if __name__ == "__main__":
    asyncio.run(main())
