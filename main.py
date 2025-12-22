import asyncio
import os
import json
from dotenv import load_dotenv
from browser_use import Browser
from utils.resume_parser import ResumeParser
from agents.matcher import MatcherAgent
from agents.researcher import ResearcherAgent

load_dotenv()

async def main():
    api_key = os.getenv("GEMINI_API_KEY")

    # 1. Parse Resume
    parser = ResumeParser(api_key=api_key)
    # Assumes your resume is in data/resume.pdf
    print("📄 Parsing Resume...")
    profile_json = await parser.parse_to_json("data/jc-resume-2025.pdf")
    profile = json.loads(profile_json)

    try:
        # 3. Researcher: Gather RAW Leads (High limit to ensure we find enough for the Matcher)
        researcher = ResearcherAgent(api_key=api_key)
        # We ask for ~60 raw items to ensure we find 10 good ones
        raw_leads = await researcher.gather_leads(profile, limit=60)

        print(f"👀 Researcher found {len(raw_leads)} raw leads. Sending to Matcher...")

        # 4. Matcher: Filter & Score (Limit to 10 verified)
        matcher = MatcherAgent(api_key=api_key)
        leads = await matcher.filter_and_score_leads(raw_leads, profile, limit=10)

        with open("data/verified_leads.json", "w") as f:
            json.dump(leads, f, indent=2)

        print(f"🏁 Done! Found {len(leads)} diversified jobs. Saved to data/verified_leads.json")

    finally:
        pass

if __name__ == "__main__":
    asyncio.run(main())
