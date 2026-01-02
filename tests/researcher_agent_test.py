import asyncio
import os
import json
from dotenv import load_dotenv
from agents.researcher import ResearcherAgent

load_dotenv()

async def main():
    # 1. Setup
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not found.")
        return

    # 2. Load the profile you parsed earlier
    profile_path = "data/profile.json"
    if not os.path.exists(profile_path):
        print(f"❌ {profile_path} not found. Run resume_parser_test.py first.")
        return

    with open(profile_path, "r") as f:
        profile = json.load(f)

    # 3. Initialize Agent (Browser is self-managed now)
    agent = ResearcherAgent(api_key=api_key)

    print(f"🚀 Robust Research started for: {profile.get('full_name')}")

    # 4. Gather Leads
    # We ask for 5 leads to keep it quick for testing
    leads = await agent.gather_leads(profile, limit=5)

    # 5. Display Results
    print(f"\n✅ LLM Found {len(leads)} potential direct listings:")
    print("-" * 60)

    for i, job in enumerate(leads, 1):
        print(f"{i}. {job.get('title')} @ {job.get('company')}")
        print(f"   URL: {job.get('url')}")
        print(f"   Direct Listing Confirmed: {job.get('is_direct_listing')}")
        print("-" * 30)

    # 6. Save for next steps (Matcher/Applier)
    output_path = "data/job_leads_minimal.json"
    with open(output_path, "w") as f:
        json.dump(leads, f, indent=2)

    print(f"\n📂 Saved leads to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
