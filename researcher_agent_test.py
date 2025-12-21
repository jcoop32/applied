import asyncio
import os
import json
from dotenv import load_dotenv
from agents.researcher import ResearcherAgent

load_dotenv()

async def main():
    # 1. Load Profile
    profile_path = "data/profile.json"
    if not os.path.exists(profile_path):
        print(f"❌ {profile_path} not found. Please run resume_parser_test.py first.")
        return

    with open(profile_path, "r") as f:
        profile = json.load(f)

    # 2. Init Agent
    api_key = os.getenv("GEMINI_API_KEY")
    agent = ResearcherAgent(api_key=api_key)

    # 3. Run Search
    # We ask for 10 jobs. The agent will read the resume to decide "Junior" vs "Senior"
    leads = await agent.gather_leads(profile, target_count=10)

    # 4. Save Results
    output_path = "data/job_leads.json"
    with open(output_path, "w") as f:
        json.dump(leads, f, indent=2)

    print(f"\n✅ Saved {len(leads)} leads to {output_path}")

    # Print preview
    print("-" * 50)
    for i, job in enumerate(leads[:5], 1):
        print(f"{i}. {job.get('title')} @ {job.get('company')}")
        print(f"   Why: {job.get('match_reason')}")
        print(f"   URL: {job.get('url')}\n")
    print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())
