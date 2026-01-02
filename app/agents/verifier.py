import json
import asyncio
from browser_use import Agent, Browser
from browser_use.llm import ChatGoogle

# Robust import for different versions
try:
    from browser_use import BrowserConfig as Config
except ImportError:
    from browser_use import BrowserProfile as Config

class VerifierAgent:
    def __init__(self, api_key, browser=None):
        self.llm = ChatGoogle(model='gemini-2.0-flash-exp', api_key=api_key)
        self.external_browser = browser

    async def verify_link(self, url):
        """Uses browser-use to navigate and visually confirm the job post."""
        print(f"👁️ Verifying: {url}")

        # Determine browser instance
        browser_to_use = self.external_browser
        is_local_browser = False

        if not browser_to_use:
            try:
                browser_to_use = Browser(config=Config(headless=True))
            except TypeError:
                browser_to_use = Browser(browser_profile=Config(headless=True))
            is_local_browser = True

        # STRICT PROMPT: Emphasize NOT changing the URL and SCROLLING
        task = (
            f"GO TO THIS EXACT URL: {url}\n"
            "DO NOT change the spelling of the URL. Use it exactly as provided.\n"
            "1. Wait for the page to load completely.\n"
            "2. SCROLL TO THE BOTTOM of the page. This is critical because the 'Apply' button is often at the footer.\n"
            "3. Analyze the page content. Look for an 'Apply', 'Apply Now', or 'Submit Application' button.\n"
            "4. Verify if this is a direct job application page for a specific role.\n"
            "5. Return ONLY a JSON object with this exact structure (no markdown formatting):\n"
            "   {{\n"
            "     \"is_valid\": bool, \n"
            "     \"has_apply_button\": bool,\n"
            "     \"reason\": str,\n"
            "     \"job_title\": str\n"
            "   }}"
        )

        agent = Agent(task=task, llm=self.llm, browser=browser_to_use)

        try:
            history = await agent.run()
            final_result = history.final_result()

            # Fix for 'NoneType' error: Check if result exists before processing
            if not final_result:
                return {
                    "is_valid": False,
                    "has_apply_button": False,
                    "reason": "Agent failed to produce a result",
                    "job_title": "Unknown",
                    "url": url
                }

            # cleanup potential markdown
            res = final_result.replace('```json', '').replace('```', '').strip()
            result_dict = json.loads(res)
            result_dict['url'] = url
            return result_dict
        except Exception as e:
            print(f"⚠️ Agent error: {e}")
            return {
                "is_valid": False,
                "has_apply_button": False,
                "reason": str(e),
                "job_title": "Unknown",
                "url": url
            }
        finally:
            if is_local_browser and browser_to_use:
                # Use a safer close check
                if hasattr(browser_to_use, 'close'):
                    await browser_to_use.close()
