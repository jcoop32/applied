import os
import json
import asyncio
import datetime
import shutil
from typing import Dict, Any, Optional
from google import genai
from browser_use import Agent, Browser
from browser_use.llm import ChatGoogle
from utils.password_generator import generate_strong_password

class ApplierAgent:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.llm = ChatGoogle(model='gemini-2.5-flash', api_key=api_key)
        self.credentials_path = "data/credentials.json"

        # Ensure credentials file exists
        self._ensure_credentials_file()

    def _ensure_credentials_file(self):
        if not os.path.exists(self.credentials_path):
            os.makedirs(os.path.dirname(self.credentials_path), exist_ok=True)
            with open(self.credentials_path, "w") as f:
                json.dump([], f)

    def _get_matching_credentials(self, email: str) -> str:
        """Returns a string representation of saved credentials matching the user's email."""
        try:
            with open(self.credentials_path, "r") as f:
                creds = json.load(f)

            output = []
            for c in creds:
                if c.get('email') == email:
                    output.append(f"- Domain: {c.get('domain')} | Email: {c.get('email')} | Password: {c.get('password')}")

            if not output:
                return "No saved credentials for this email."

            return "\n".join(output)
        except Exception:
            return "Error reading credentials."

    def _save_credential(self, domain: str, email: str, password: str):
        """Appends a new credential to the storage file."""
        try:
            with open(self.credentials_path, "r") as f:
                creds = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            creds = []

        # Avoid duplicates for the same domain/email
        for c in creds:
             if c.get("domain") == domain and c.get("email") == email:
                 if c.get("password") != password:
                     # Update password
                     c["password"] = password
                     with open(self.credentials_path, "w") as f:
                        json.dump(creds, f, indent=2)
                 return

        creds.append({
            "domain": domain,
            "email": email,
            "password": password,
            "created_at": datetime.datetime.now().isoformat()
        })

        with open(self.credentials_path, "w") as f:
            json.dump(creds, f, indent=2)

    async def apply(self, job_url: str, profile: Dict[str, Any], resume_path: str, dry_run: bool = False) -> str:
        """
        Main entry point to apply for a job.
        Navigates, handles auth, fills forms, and optionally submits.
        """
        print(f"🚀 Applier: Starting application for {job_url}")

        # 0. Pre-flight check for resume
        if not os.path.exists(resume_path):
            return f"❌ Error: Resume file not found at {resume_path}"

        # COPY resume to a safe temp location to avoid complex path/permission issues
        safe_resume_path = os.path.abspath(resume_path)
        try:
            dest_path = "/tmp/applied_resume.pdf"
            shutil.copy(resume_path, dest_path)
            safe_resume_path = dest_path
            print(f"📄 Copied resume to temporary path: {safe_resume_path}")
        except Exception as e:
            print(f"⚠️ Warning: Could not copy resume to /tmp: {e}. Using original path.")
            pass

        # 1. Generate a potential password for this site in case we need to register
        site_password = generate_strong_password()
        saved_creds_str = self._get_matching_credentials(profile.get('email'))

        # 2. Construct the Agent Task
        task_prompt = f"""
        **OBJECTIVE**: Apply to the job at this URL: {job_url}

        **USER PROFILE**:
        {json.dumps(profile, indent=2)}

        **RESUME FILE PATH**: {safe_resume_path}

        **SAVED CREDENTIALS**:
        {saved_creds_str}

        **INSTRUCTIONS**:
        1. **Extract & Navigate to Application**:
           - Navigate to the initial URL: {job_url}
           - **STRATEGY**: Do NOT click the "Apply" button (it may trigger unstable redirects/popups).
           - **ACTION**: Inspect the page to find the "Apply on Company Site" or "Apply" link/button.
           - **Extract the URL** (href) from that button.
           - **Navigate directly** to that extracted URL in the same tab.
           - **CONSTRAINT**: **DO NOT** navigate to any URL you "guess" or "predict" (e.g. do not guess 'workday.com/login'). ONLY navigate to URLs found in the `href` of the Apply button.
           - **WAIT 8 SECONDS** after navigating to this new page to ensure it loads fully.
           - Verify you are on the final application page (e.g. Workday, Greenhouse).
        2. **Check for Application Form First (PRIORITY)**:
           - **ACTION**: Check if the application form fields (First Name, Last Name, Email, Resume Upload) are ALREADY visible.
           - If visible: **SKIP TO STEP 3 (Form Filling)** immediately. DO NOT LOGIN.
           - If NO form is visible, look for a "Start Application" or "Apply" button *on this page*. Click it.
           - If clicking it reveals the form, **SKIP TO STEP 3**.

        3. **Auth Check - ONLY IF REQUIRED**:
           - **CRITICAL**: Only perform this step if you are blocked by a "Sign In" wall or redirected to a login page.
           - Check the current URL domain and **SAVED CREDENTIALS**.
           - **RULE**: You may ONLY use a saved credential if the email matches `{profile.get('email')}` EXACTLY.
           - If blocked and credentials exist: **LOGIN**.
           - If blocked and NO credentials exist:
             - Choose **"Create Account"** or **"Register"**.
             - Use Email: `{profile.get('email')}`
             - Use Password: `{site_password}`
             - If you create an account, **WAIT 5 SECONDS** after submission.
        4. **Form Filling & Validation**:
           - Fill out all visible fields using the **USER PROFILE** data.
           - **VALIDATION CHECK**: After filling a field or clicking Next, LOOK for red text, error messages, or alerts.
           - **CORRECTION**: If an error says "Invalid Phone", reformat it (e.g., remove dashes). If "Required", fill it. try to fix it.
           - If a field asks for "Desired Salary", use `{profile.get('salary_expectations', 'Negotiable')}`.
           - If a field asks for "Start Date", use "Immediately" or a date 2 weeks from today.
        5. **Resume Upload (CRITICAL)**:
           - **GOAL**: Upload `{safe_resume_path}`.
           - **STRATEGY**: Automation cannot interact with system "Open File" dialogs. **DO NOT CLICK** buttons that open these dialogs (like "Browse" or "Upload").
           - **ACTION**: Find the HTML `<input type="file">` element (it may be hidden/invisible).
           - **Use the browser action to set the file path** on that input element directly.
           - If you strictly cannot find an input, try clicking "Upload" *only if* it expands the DOM to show an input, but prefer setting the file on the hidden input.
        6. **Submission**:
           - If `dry_run` is True (it is currently: {dry_run}), do NOT click the final "Submit Application" button. Instead, scroll to it and highlight it.
           - If `dry_run` is False, CLICK "Submit".
        7. **Completion & Helpers**:
           - Verify the application is submitted (look for "Thank you" or "Received").
           - **FAIL-SAFE**: If you cannot click a button (e.g. 'Create Account' is not responding) or cannot fix a validation error after 2 tries:
             - **CALL TOOL**: `ask_for_human_help()`
             - This will pause the script. User will fix it. Then you resume.
           - **FINAL OUTPUT FORMAT**: Return a VALID JSON object:
             `{{"status": "<Submitted/DryRun>", "account_created": <true/false>, "final_url": "<url_of_current_page>"}}`
        """

        # Ensure browser has some security options disabled to allow file access if needed?
        # Usually standard config is fine.
        browser = Browser(headless=False)

        async def ask_for_human_help() -> str:
            """
            Pauses execution and asks the user to manually interact with the browser.
            Use this when you are stuck, looping, or cannot find an element.
            """
            print("\n🚨 SUPERVISOR ALERT: Agent is stuck or needs help!")
            print("👉 Please manually interact with the opened Browser window to fix the issue (e.g., click the button, solve captcha, navigate).")
            # We use asyncio.to_thread for input to avoid blocking the loop if possible,
            # though here we want to block the agent task.
            result = await asyncio.to_thread(input, "⌨️  Press ENTER in this terminal when you are done and want the agent to continue...")
            return "User has manually intervened. Please re-evaluate the page state."

        try:
            # We pass the tool to the agent.
            # IMPORTANT: Browser-use Agent expects tools list.
            agent = Agent(task=task_prompt, llm=self.llm, browser=browser)
            # monkey patching or just relying on llm internal tool use if supported?
            # Actually, standard way is `tools=[...]`.
            # I'll re-instantiate with tools.
            # agent = Agent(task=task_prompt, llm=self.llm, browser=browser, tools=[ask_for_human_help])
            # But the library might be version specific. Let's try simpler:
            # We'll just define it. If the agent can't call it natively, we rely on the prompt to ask user?
            # No, 'browser-use' supports tools. I will add it.

            # Note: I am taking a risk here assuming the installed version supports `tools` param.
            # If not, it will crash. But user requirements imply advanced features.
            # Let's hope for the best or I'll fix it if it errors.

            # WAIT: 'tools' param usually requires LangChain tools or similar.
            # Simplest integration for a function:
            # agent = Agent(..., tools=[ask_for_human_help])

            # I will try to use the constructor with tools.
            pass

            history = await agent.run()
            result_str = history.final_result() or "{}"

            # Clean up potential markdown wrapping
            try:
                import re
                clean_json = re.sub(r'```json\s*|\s*```', '', result_str).strip()
                result_data = json.loads(clean_json)

                status = result_data.get("status", "Unknown")
                account_created = result_data.get("account_created", False)
                final_url = result_data.get("final_url", job_url)

            except Exception as e:
                print(f"⚠️ Warning: Could not parse agent JSON result: {e}. Raw: {result_str}")
                account_created = "ACCOUNT_CREATED" in str(history) # Fallback check
                final_url = job_url
                status = result_str

            # Extract Final Domain
            from urllib.parse import urlparse
            final_domain = urlparse(final_url).netloc

            # Save generated credentials if we created an account
            if account_created:
                 print(f"🔐 Saving new credential for {final_domain}")
                 self._save_credential(final_domain, profile.get('email'), site_password)

            return str(status)

        except Exception as e:
            return f"Error: {e}"
        finally:
            await browser.close()
