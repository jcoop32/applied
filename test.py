import asyncio
import os
# CHANGE THIS LINE: Import BrowserConfig from the top level
from browser_use import Agent, Browser
from browser_use.llm import ChatGoogle
from dotenv import load_dotenv

load_dotenv()

async def main():
    # Define where cookies will be stored
    data_dir = os.path.join(os.getcwd(), "linkedin_session")

    # Configure the browser
    browser = Browser()

    llm = ChatGoogle(model='gemini-2.5-flash', api_key=os.getenv("GEMINI_API_KEY"))

    task = (
        "1. Go to https://www.linkedin.com/login\n"
        "2. Wait for the user (me) to log in manually.\n"
        "3. Once I am on the home feed, tell me 'Session Saved' and stop."
    )

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
    )

    print("🚀 Opening LinkedIn... Please log in manually in the browser window.")

    await agent.run()

    # Close explicitly to ensure cookies flush to disk
    try:
        await browser.close()
    except AttributeError:
        pass

if __name__ == "__main__":
    asyncio.run(main())
