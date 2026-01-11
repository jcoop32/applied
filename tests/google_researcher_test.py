import asyncio
import os
import json
from dotenv import load_dotenv
from app.agents.google_researcher import GoogleResearcherAgent

load_dotenv()

async def main():
    # 1. Setup
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not found.")
        return

    # 2. Mock Profile
    profile = {
        "full_name": "Test User",
        "location": "San Francisco, CA",
        "skills": ["Python", "React", "AWS"],
        "experience": [],
        "raw_text": "Experienced Python Software Engineer looking for backend roles."
    }

    # 3. Initialize Agent
    agent = GoogleResearcherAgent(api_key=api_key)

    print(f"🚀 Google Research started for: {profile.get('full_name')}")

    # 4. Gather Leads - override job title to be specific
    # Using a small limit
    leads = await agent.gather_leads(profile, limit=5, job_title="Senior Software Engineer")

    # 5. Display Results
    print(f"\n✅ Google Verified Agent Found {len(leads)} leads:")
    print("-" * 60)

    for i, job in enumerate(leads, 1):
        print(f"{i}. {job.get('title')} @ {job.get('company')}")
        print(f"   URL: {job.get('url')}")
        print(f"   Snippet: {job.get('snippet')[:100]}...")
        print("-" * 30)

if __name__ == "__main__":
    asyncio.run(main())
