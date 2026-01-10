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
from app.utils.password_generator import generate_strong_password
from app.services.supabase_client import supabase_service

class ApplierAgent:
    def __init__(self, api_key: str, headless: bool = False):
        self.api_key = api_key
        self.headless = headless
        self.llm = ChatGoogle(model='gemini-2.5-flash', api_key=api_key)
        # Credentials now handled via Supabase

    def _get_matching_credentials(self, email: str) -> str:
        """Returns a string representation of saved credentials matching the user's email."""
        try:
            creds = supabase_service.get_credentials(email)

            output = []
            for c in creds:
                output.append(f"- Domain: {c.get('domain')} | Email: {c.get('email')} | Password: {c.get('password')}")

            if not output:
                return "No saved credentials for this email."

            return "\n".join(output)
        except Exception:
            return "Error reading credentials."

    def _save_credential(self, domain: str, email: str, password: str):
        """Appends a new credential to the database."""
        supabase_service.save_credential(domain, email, password)

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

    async def apply(self, job_url: str, profile: Dict[str, Any], resume_path: str, dry_run: bool = False, lead_id: int = None) -> str:
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
        
        if lead_id:
            supabase_service.update_lead_status(lead_id, "NAVIGATING")

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
           - Calls `update_status("Analyzying Page")`.

        2. **Quick Apply Check & T&C (CRITICAL)**:
           - Look for "Apply", "Apply Now", "Start Application".
           - **CRITICAL**: CHECK FOR AND CLICK 'I Agree', 'Terms of Service', 'Consent', or 'Privacy Policy' CHECKBOXES. 
           - **RULE**: You MUST explicitly look for `input[type='checkbox']` that might be required before finding the Apply button.
           - If Apply button is found, click it.
           - Calls `update_status("Starting Application")`.

        3. **Auth (Only if blocked)**:
           - If blocked by a "Sign In" wall:
             - Calls `update_status("Handling Authentication")`.
             - Use saved credentials if email matches `{profile.get('email')}`.
             - Else, **Create Account** with:
               - Email: `{profile.get('email')}`
               - Password: `{site_password}`
             - **Hover** 1s before clicking "Create Account".

        4. **Verification / 2FA / CAPTCHA (INTERACTIVE)**:
           - **IF** you see a screen asking for a "Verification Code", "2FA", "OTP", or an unsolvable CAPTCHA:
             - **STOP**. Do NOT try to guess.
             - Call `ask_user_tool("Enter the verification code sent to email")`.
             - **WAIT** for the tool to return the code.
             - Input the code and continue.

        5. **Resume Upload (Top Priority)**:
           - Calls `update_status("Uploading Resume")`.
           - **GOAL**: Upload `{safe_resume_path}` to the resume field.
           - **METHOD**:
             - **Scan the DOM** for `<input type="file">`.
             - **ACTION**: Use the browser's `upload_file(path="{safe_resume_path}")` action targeting that input.
             - **CRITICAL**: DO NOT click the "Upload Resume" button if it opens a system dialog. You MUST target the `input` element directly.
             - **FALLBACK**: If the `input` is hidden, try to locate the visible "Upload" button/label, but still attempt to use the `upload_file` action on the associated hidden input if possible.
           - **VERIFY**: Check if the file name appears or a "Remove" icon shows up.

        6. **Form Filling (Comprehensive)**:
           - Calls `update_status("Filling Form")`.
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

        7. **Voluntary Disclosures**:
           - Gender: `{profile.get('Voluntary Questions Answers', {}).get('Gender', 'Decline to identify')}`
           - Race: `{profile.get('Voluntary Questions Answers', {}).get('Race', 'Decline to identify')}`
           - Veteran: `{profile.get('Voluntary Questions Answers', {}).get('Veteran Status', 'No')}`
           - Disability: `{profile.get('Voluntary Questions Answers', {}).get('Disability Status', 'No')}`

        8. **Submission & Validation**:
           - **LOOP (Max 3 attempts)**:
             1. **Hover** over "Submit"/"Apply" for 1s.
             2. **CRITICAL PRE-SUBMIT CHECK**: Scour the page for "I Agree" / "Terms" checkboxes again. Click them if unchecked.
             3. Click "Submit".
             4. **WAIT 3 SECONDS**.
             5. **SCAN FOR ERRORS**: Look for red text, "Required field", or "Invalid".
             6. **IF ERRORS**: **FIX THEM**. Focus on the empty required fields. REPEAT.
             7. **IF SUCCESS**: Stop.

        9. **Output**:
           - Return JSON: `{{ "status": "<Submitted/DryRun/Failed>", "account_created": <true/false>, "final_url": "<url>" }}`
        """

        # Ensure browser has some security options disabled to allow file access if needed?
        # Usually standard config is fine.
        browser = Browser(headless=self.headless)

        async def ask_user_tool(prompt: str) -> str:
            """
            Pauses and asks the user for a verification code or input via Supabase.
            Polls for a response.
            """
            print(f"\\n🔐 AGENT ASKING USER: {prompt}")
            if lead_id:
                supabase_service.request_verification(lead_id, "MANUAL_INTERACTION", prompt)
            
            # Polling loop
            max_retries = 60 # 5 minutes (5s * 60)
            for i in range(max_retries):
                print(f"⏳ Waiting for user input... ({i+1}/{max_retries})")
                await asyncio.sleep(5)
                
                if lead_id:
                    resp = supabase_service.check_verification(lead_id)
                    if resp:
                        print(f"✅ Received user input: {resp}")
                        return resp
                
                # Check for local terminal override (legacy/debug)
                # ... avoiding blocking input() calls in async if not needed
            
            return "TIMEOUT: User did not respond."

        async def update_status_tool(status: str) -> str:
            """Updates the visible status of the application for the user."""
            print(f"🔄 STATUS UPDATE: {status}")
            if lead_id:
                supabase_service.update_lead_status(lead_id, status)
            return "Status updated"

        try:
            # Initialize Controller
            from browser_use import Controller
            controller = Controller()
            
            # Register tools via the registry
            action = controller.registry.action
            
            @action("Ask User for Input")
            async def ask_user_action(prompt: str):
                return await ask_user_tool(prompt)

            @action("Update Application Status")
            async def update_status_action(status: str):
                return await update_status_tool(status)

            agent = Agent(
                task=task_prompt, 
                llm=self.llm, 
                browser=browser, 
                available_file_paths=[safe_resume_path],
                controller=controller
            )

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
            if result_data.get("status") == "APPLIED" or account_created:
                 if supabase_service:
                     print(f"✅ Marking lead as APPLIED: {resolved_url}")
                     if lead_id:
                         supabase_service.update_lead_status(lead_id, "APPLIED")
                     else:
                         u_id = profile.get('user_id') or profile.get('id')
                         if u_id:
                             supabase_service.update_lead_status_by_url(u_id, job_url, "APPLIED")

            return str(status)

        except Exception as e:
            return f"Error: {e}"
        finally:
            try:
                if hasattr(browser, 'close'):
                    await browser.close()
            except Exception:
                pass
