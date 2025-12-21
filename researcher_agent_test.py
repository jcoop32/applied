import asyncio
import os
import json
from dotenv import load_dotenv
from agents.researcher import ResearcherAgent

load_dotenv()

async def main():
    # 1. Load your Identity
    try:
        with open("data/profile.json", "r") as f:
            profile = json.load(f)
    except FileNotFoundError:
        print("❌ Error: profile.json not found. Run the resume parser first!")
        return

    # 2. Initialize Agent
    agent = ResearcherAgent(api_key=os.getenv("GEMINI_API_KEY"))

    # 3. Search for Jobs
    # You can add extra search terms here like "Fintech" or "Startup"
    job_leads = await agent.gather_leads(profile, search_query_extra="focus on Python Backend roles")

    # 4. Save the "Hit List"
    with open("data/job_leads.json", "w") as f:
        json.dump(job_leads, f, indent=2)

    print(f"\n✅ Found {len(job_leads)} job leads!")
    for idx, job in enumerate(job_leads, 1):
        print(f"{idx}. {job['title']} at {job['company']}")
        print(f"   Link: {job['url']}\n")

if __name__ == "__main__":
    asyncio.run(main())
