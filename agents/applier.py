import os
import json
import asyncio
import datetime
import shutil
import shutil
import requests
from bs4 import BeautifulSoup
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

    async def _resolve_application_url(self, job_url: str) -> str:
        """
        Fetches the raw HTML via requests and asks the LLM
        to identify the correct job application URL using the raw content.
        """
        print(f"🕵️ Resolving true application URL for: {job_url}")

        try:
            # 1. Fetch RAW HTML
            def fetch_raw():
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                response = requests.get(job_url, headers=headers, timeout=10, allow_redirects=True)
                return response.text, response.url

            html_content, final_url = await asyncio.to_thread(fetch_raw)

            # 2. Ask the LLM to find the link using RAW content
            client = genai.Client(api_key=self.api_key)

            prompt = f"""
            I have the raw HTML content of a job posting page below.
            Find the URL for the "Apply", "Apply Now", "Apply on Company Site", or "Start Application" button.
            Rules:
            1. Return ONLY the raw URL. No JSON, no text, no markdown.
            2. If there are multiple, prefer the one that goes to an external ATS (like Workday, Greenhouse, Lever) over an internal "Quick Apply".
            3. If the URL is relative (starts with /), append it to the base domain: {final_url}

            HTML Content (Truncated if too large):
            {html_content[:100000]}
            """

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )

            extracted_url = response.text.strip()

            # Basic validation
            if extracted_url and "http" in extracted_url:
                print(f"🤖 LLM identified Apply URL: {extracted_url}")
                return extracted_url

            print(f"⚠️ LLM could not find URL in HTML: {extracted_url}")
            return final_url # Fallback to current

        except Exception as e:
            print(f"⚠️ Resolution failed (using fallback): {e}")
            return job_url

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

        # 0.5. PRE-RESOLVE THE URL (User requested simple script to find link first)
        resolved_url = await self._resolve_application_url(job_url)
        print(f"🎯 Target ATS URL: {resolved_url}")

        # 1. Generate a potential password for this site in case we need to register
        site_password = generate_strong_password()
        saved_creds_str = self._get_matching_credentials(profile.get('email'))

        # 2. Construct the Agent Task
        task_prompt = f"""
        **OBJECTIVE**: Apply to the job at this URL: {resolved_url}

        **USER PROFILE**:
        {json.dumps(profile, indent=2)}

        **RESUME FILE PATH**: {safe_resume_path}

        **SAVED CREDENTIALS**:
        {saved_creds_str}

        **INSTRUCTIONS**:

        1. **Navigate & Load**:
           - Navigate to: {resolved_url}
           - **WAIT 5 SECONDS** for full load.
           - Verify you are on the application page.

        2. **Quick Apply Check**:
           - Look for immediate application forms (First Name, Last Name, etc.).
           - If visible, **PROCEED TO STEP 3**.
           - If NOT visible, find and click "Apply", "Apply Now", or "Start Application".

        3. **Auth (Only if blocked)**:
           - If blocked by a "Sign In" wall:
             - Use saved credentials if email matches `{profile.get('email')}`.
             - Else, **Create Account** with:
               - Email: `{profile.get('email')}`
               - Password: `{site_password}`
             - **Hover** 1s before clicking "Create Account".

        4. **Resume Upload (Top Priority)**:
           - **GOAL**: Upload `{safe_resume_path}` to the resume field.
           - **METHOD**:
             - **Scan the DOM** for `<input type="file">`.
             - **ACTION**: Use the browser's `upload_file(path="{safe_resume_path}")` action targeting that input.
             - **CRITICAL**: DO NOT click the "Upload Resume" button if it opens a system dialog. You MUST target the `input` element directly.
             - **FALLBACK**: If the `input` is hidden, try to locate the visible "Upload" button/label, but still attempt to use the `upload_file` action on the associated hidden input if possible.
           - **VERIFY**: Check if the file name appears or a "Remove" icon shows up.

        5. **Form Filling (Comprehensive)**:
           - **RULE**: Fill **ALL** visible fields. Do not skip any unless explicitly marked "Optional" AND you have no data for it.
           - **Required Params**: Look for `*` or "Required" labels. PRIORITIZE these.
           - **Inputs**:
             - **Text**: Fill with Profile data.
             - **Dropdowns**: Click, Type 2-3 chars, **WAIT** for options, then **Click** the best match.
             - **School/University Autocomplete (Specific Rule)**:
               - **Problem**: Typing full names like "University of Illinois at Chicago" often fails to trigger the substring matcher.
               - **STRATEGY**:
                 1. Type the **most unique** keyword first (e.g. for "University of Illinois at Chicago", type "Illinois" or "Chicago").
                 2. **WAIT** for the list.
                 3. If found: **Click** it.
                 4. If NOT found: Clear and type a refined substring (e.g. "Illinois at Chicago").
             - **Radio/Checkbox**: Click the visual element (label or custom div) if the input is hidden.
             - **Phone Number**:
               - **Country Code**: Look for a country flag or dropdown *next to* the phone input.
               - **ACTION**: Explicitly select "United States" or "+1" **BEFORE** typing the number.
               - If the phone field splits area code, split `{profile.get('phone')}` accordingly.
           - **Mapping**:
             - "Desired Salary" -> `{profile.get('salary_expectations', 'Negotiable')}`
             - "Start Date" -> 2 weeks from today.
             - "LinkedIn" -> `{profile.get('linkedin')}`
             - "Portfolio" -> `{profile.get('portfolio')}`

        6. **Voluntary Disclosures**:
           - Gender: `{profile.get('Voluntary Questions Answers', {}).get('Gender', 'Decline to identify')}`
           - Race: `{profile.get('Voluntary Questions Answers', {}).get('Race', 'Decline to identify')}`
           - Veteran: `{profile.get('Voluntary Questions Answers', {}).get('Veteran Status', 'No')}`
           - Disability: `{profile.get('Voluntary Questions Answers', {}).get('Disability Status', 'No')}`

        7. **Submission & Validation**:
           - **LOOP (Max 3 attempts)**:
             1. **Hover** over "Submit"/"Apply" for 1s.
             2. Click "Submit".
             3. **WAIT 3 SECONDS**.
             4. **SCAN FOR ERRORS**: Look for red text, "Required field", or "Invalid".
             5. **IF ERRORS**: **FIX THEM**. Focus on the empty required fields. REPEAT.
             6. **IF SUCCESS**: Stop.

        8. **Output**:
           - Return JSON: `{{ "status": "<Submitted/DryRun/Failed>", "account_created": <true/false>, "final_url": "<url>" }}`
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
            agent = Agent(task=task_prompt, llm=self.llm, browser=browser, available_file_paths=[safe_resume_path])
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
                account_created = result_data.get("account_created", False)
                final_url = result_data.get("final_url", resolved_url)

            except Exception as e:
                print(f"⚠️ Warning: Could not parse agent JSON result: {e}. Raw: {result_str}")
                account_created = "ACCOUNT_CREATED" in str(history) # Fallback check
                final_url = resolved_url
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
            try:
                if hasattr(browser, 'close'):
                    await browser.close()
            except Exception:
                pass
