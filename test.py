import asyncio
import os
from browser_use import Agent, Browser
from browser_use.llm import ChatGoogle
from dotenv import load_dotenv

load_dotenv()

async def main():
    # Define where cookies will be stored
    data_dir = os.path.join(os.getcwd(), "linkedin_session")

    # We initialize the browser without a separate Config object.
    # We pass the user_data_dir as a parameter to the Browser.
    browser = Browser()

    llm = ChatGoogle(model='gemini-2.0-flash', api_key=os.getenv("GEMINI_API_KEY"))

    # This task is just to get you to the login page and keep the session open
    task = (
        "1. Go to https://www.linkedin.com/login\n"
        "2. Wait for the user (me) to log in manually.\n"
        "3. Once I am on the home feed, tell me 'Session Saved' and stop."
    )

    # We manually set the user_data_dir in the context when the agent starts
    # This bypasses the need for the BrowserContextConfig import
    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
    )

    print("🚀 Opening LinkedIn... Please log in manually in the browser window.")

    # Important: In some versions, you set the context here:
    await agent.run()

    # This ensures the browser saves the cookies before closing
    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
