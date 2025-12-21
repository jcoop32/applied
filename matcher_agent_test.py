import asyncio
import os
import json
from dotenv import load_dotenv
from agents.matcher import MatcherAgent
from browser_use import Agent, Browser
from browser_use.llm import ChatGoogle

load_dotenv()

async def main():
    api_key = os.getenv("GEMINI_API_KEY")
    matcher = MatcherAgent(api_key=api_key)
    llm = ChatGoogle(model='gemini-2.5-flash', api_key=api_key)

    with open("data/job_leads.json", "r") as f:
        leads = json.load(f)
    with open("data/profile.json", "r") as f:
        profile = json.load(f)

    ranked_leads = []

    # Let's try the first 3 leads
    for job in leads[:3]:
        print(f"🧐 Processing: {job['title']} at {job['company']}...")

        # We use a fresh browser instance for each lead to stay clean
        browser = Browser()
        agent = Agent(
            task=f"Go to {job['url']} and extract the full job description text.",
            llm=llm,
            browser=browser
        )

        try:
            history = await agent.run()
            jd_text = history.final_result()

            if "not available" in jd_text.lower() or "not found" in jd_text.lower():
                print(f"⚠️ Job no longer active: {job['title']}")
                continue

            # Get the match score from our Matcher Agent
            analysis = await matcher.score_job(profile, jd_text)
            job.update(analysis)
            ranked_leads.append(job)
            print(f"✅ Scored: {job['match_score']}%")

        except Exception as e:
            print(f"❌ Error matching {job['title']}: {e}")

    # Save the ranked leads
    with open("data/ranked_jobs.json", "w") as f:
        json.dump(ranked_leads, f, indent=2)

    print("\n🏆 Rankings saved to data/ranked_jobs.json")

if __name__ == "__main__":
    asyncio.run(main())
