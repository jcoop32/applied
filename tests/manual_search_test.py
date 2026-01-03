import asyncio
import os
import json
from dotenv import load_dotenv
from app.agents.researcher import ResearcherAgent

load_dotenv()

async def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not found.")
        return

    # Mock Profile
    profile = {
        "full_name": "Test User",
        "location": "San Francisco, CA"
    }

    agent = ResearcherAgent(api_key=api_key)

    print("\n--- Test 1: Manual Override ---")
    print("Simulating search for 'Chef' in 'Paris, TX'")
    leads_manual = await agent.gather_leads(
        profile,
        limit=2,
        job_title="Chef",
        location="Paris, TX"
    )

    print(f"\nFound {len(leads_manual)} leads.")
    if leads_manual:
        print(f"Sample Lead: {leads_manual[0].get('title')} in {leads_manual[0].get('location', 'Unknown')} (Query: {leads_manual[0].get('query_source')})")

    print("\n--- Test 2: Default Behavior ---")
    print("Simulating default search based on profile (San Francisco)")
    # Should use generated strategy (likely empty fallback if profile is minimal, or generic)
    # Actually Researcher agent generates 'Software Engineer' if profile empty fallback is hit,
    # but here we pass minimal profile. LLM might generate something.
    leads_default = await agent.gather_leads(profile, limit=2)
    print(f"\nFound {len(leads_default)} leads.")
    if leads_default:
         print(f"Sample Lead Query Source: {leads_default[0].get('query_source')}")

if __name__ == "__main__":
    asyncio.run(main())
