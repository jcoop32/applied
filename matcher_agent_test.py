import asyncio
import os
import json
from dotenv import load_dotenv
from agents.matcher import MatcherAgent
# CHANGE THIS LINE:
from browser_use import Agent, Browser, BrowserConfig
from browser_use.llm import ChatGoogle

load_dotenv()

async def main():
    api_key = os.getenv("GEMINI_API_KEY")
    matcher = MatcherAgent(api_key=api_key)
    llm = ChatGoogle(model='gemini-2.5-flash', api_key=api_key)

    # Use the SAME directory as test.py
    data_dir = os.path.join(os.getcwd(), "linkedin_session")

    print(f"📂 Using browser session at: {data_dir}")

    # Initialize Browser with the saved session
    browser = Browser(config=BrowserConfig(
        user_data_dir=data_dir,
        headless=False
    ))

    try:
        with open("data/job_leads.json", "r") as f:
            leads = json.load(f)
        with open("data/profile.json", "r") as f:
            profile = json.load(f)

        # Process leads...
        # (Rest of your loop code remains the same)

    finally:
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
