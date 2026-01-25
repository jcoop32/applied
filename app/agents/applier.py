import os
import json
import asyncio
import datetime
import shutil
import shutil
import logging
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional
from google import genai
from browser_use import Agent, Browser
from browser_use.llm import ChatGoogle
from app.utils.password_generator import generate_strong_password
from app.services.supabase_client import supabase_service
from app.services.log_stream import log_stream_manager
from app.services.browser_resolver import resolver

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





    async def apply(self, job_url: str, profile: Dict[str, Any], resume_path: str, dry_run: bool = False, lead_id: int = None, use_managed_browser: bool = False, session_id: int = None, instructions: str = None) -> str:
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
        resolved_url = await resolver.resolve_job_url(job_url)
        print(f"🎯 Target ATS URL: {resolved_url}")
        
        if lead_id:
            # Determine execution mode for status visibility
            mode_label = "Standard"
            if use_managed_browser:
                mode_label = "Managed-Cloud"
            elif os.getenv("GITHUB_ACTIONS"):
                mode_label = "GHA"
            
            supabase_service.update_lead_status(lead_id, f"NAVIGATING ({mode_label})")

        # 1. Generate a potential password for this site in case we need to register
        site_password = generate_strong_password()
        saved_creds_str = self._get_matching_credentials(profile.get('email'))

        # 2. Construct the Agent Task
        captcha_instruction = (
            " - **CLOUD MODE DETECTED**: The Cloud Browser acts as a persistent human. **WAIT 15 SECONDS**. Do NOT stop. The cloud system often solves it automatically."
            if use_managed_browser else
            " - **IF IT FAILS OR REQUIRES SOLVING A PUZZLE**: \n               - **STOP IMMEDIATELY**. Do NOT try to guess. Do NOT ask user for help (they cannot see the screen).\n               - **RETURN FAILURE JSON**: `{{ \"status\": \"FAILED\", \"reason\": \"Visual CAPTCHA detected and blocked automation.\" }}`"
        )

        user_instructions_block = ""
        if instructions:
            user_instructions_block = f"\n        **USER INSTRUCTIONS FOR THIS JOB**:\n        {instructions}\n"

        task_prompt = f"""
        **OBJECTIVE**: Apply to the job at this URL: {resolved_url}

        **USER PROFILE**:
        {json.dumps(profile, indent=2)}

        **RESUME FILE PATH**: {safe_resume_path}

        **SAVED CREDENTIALS**:
        {saved_creds_str}

{user_instructions_block}

         **STRICT INTERACTION RULES**:
            - **Dropdowns**: 
              1. Click the dropdown element.
              2. Type 2-3 characters of the target value.
              3. **WAIT 1 SECOND**.
              4. Press 'ArrowDown'.
              5. Press 'Enter'.
              - **DO NOT** just type text into the container without selecting.
            - **Authentication**:
              - After clicking "Create Account" or "Sign In", **WAIT 10 SECONDS** before attempting to fill any new form fields.

         **INSTRUCTIONS**:

        1. **Navigate & Load**:
           - Navigate to: {resolved_url}
           - **WAIT 5 SECONDS** for full load.
           - Calls `update_status("Analyzying Page")`.

        2. **School / University Selection (CRITICAL)**:
           - When asked for University/School, search for: **"Illinois Institute of Technology"**.
           - **DO NOT** select "IIT" or other abbreviations unless they match exactly.
           - If it's a dropdown, type "Illinois Inst" and wait for the autocomplete.


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

        4. **Verification / 2FA / CAPTCHA (CRITICAL RULES)**:
           - **Case A: Email/SMS Code**: 
             - If asked for a code sent to email/phone, Call `ask_user_tool("Enter the verification code sent to email")`.
             - **WAIT** for the tool to return the code.
           - **Case B: Visual CAPTCHA (Images, Puzzle, Cloudflare)**:
             - Try to click the check box *once*.
             {captcha_instruction}

        5. **Resume Upload (Top Priority)**:
           - Calls `update_status("Uploading Resume")`.
           - **GOAL**: Upload `{safe_resume_path}` to the resume field.
           - **METHOD**:
             - **Scan the DOM** for `<input type="file">`.
             - **ACTION**: Use the browser's `upload_file(path="{safe_resume_path}")` action targeting that input.
             - **CRITICAL**: DO NOT click the "Upload Resume" button if it opens a system dialog. You MUST target the `input` element directly.
             - **VERIFICATION**:
               - After uploading, **WAIT 3 SECONDS**.
               - Look for success indicators (e.g. filename visible, "Uploaded") OR failure messages ("File too large", "Failed to upload", "Invalid format").
               - **IF FAILURE DETECTED**:
                 - **STOP IMMEDIATELY**.
                 - **RETURN FAILURE JSON**: `{{ "status": "FAILED", "reason": "Resume upload failed: <error message found>" }}`

        6. **Form Filling (Comprehensive)**:
           - Calls `update_status("Filling Form")`.
           - **RULE**: Fill **ALL** visible fields. Do not skip any unless explicitly marked "Optional" AND you have no data for it.
           - **Inputs**:
             - **Text**: Fill with Profile data.
             - **Dropdowns**: FOLLOW STRICT RULE ABOVE (Click -> Type -> Wait -> ArrowDown -> Enter).
             - **Phone Number**: 
               - **IMPORTANT**: Click the input field first.
               - If there is a separate country code dropdown, select **"+1 (United States)"** BEFORE typing the number.
               - Enter number: `{profile.get('phone')}`

           - **Mapping**:
             - "Desired Salary" -> `{profile.get('salary_expectations', 'Negotiable')}`
             - "Start Date" -> 2 weeks from today.
             - "LinkedIn" -> `{profile.get('linkedin')}`
             - "Portfolio" -> `{profile.get('portfolio')}`

        7. **Submission & Validation**:
           - **LOOP (Max 3 attempts)**:
             1. **Hover** over "Submit"/"Apply" for 1s.
             2. **CRITICAL PRE-SUBMIT CHECK**: 
                - Review the form for empty mandatory fields (marked with *).
                - Scour the page for "I Agree" / "Terms" checkboxes again. Click them if unchecked.
             3. Click "Submit".

             4. **WAIT 3 SECONDS**.
             5. **SCAN FOR ERRORS**: Look for red text, "Required field", or "Invalid".
             6. **IF ERRORS**: **FIX THEM**. Focus on the empty required fields. REPEAT.
             7. **IF SUCCESS**: Stop.

        8. **Output (MANDATORY)**:
           - **YOU MUST RETURN VALID JSON AT THE END. DO NOT RETURN PLAIN TEXT.**
           - **Success Format**: `{{ "status": "APPLIED", "account_created": <true/false>, "final_url": "<url>" }}`
           - **Failure Format**: `{{ "status": "FAILED", "reason": "<Short explanation of why it failed>" }}`
        """

        # Ensure browser has some security options disabled to allow file access if needed?
        # Usually standard config is fine.
        # Ensure browser has some security options disabled to allow file access if needed?
        # Usually standard config is fine.
        
        # FIX: Strict check for managed browser + API key. Do NOT auto-enable just because key exists.
        has_bu_key = bool(os.getenv("BROWSER_USE_API_KEY"))
        print(f"🕵️ Debug: use_managed_browser={use_managed_browser}, has_key={has_bu_key}")

        if use_managed_browser and has_bu_key:
            print("☁️ Using Browser Use Cloud for enhanced stealth")
            # Cloud browser does not support 'headless' arg in the same way, usually handled remote
            browser = Browser(use_cloud=True)

            try:
                # Attempt to get session ID for live view
                # This depends on browser-use internals, assuming browser.session_id or browser.config.session_id
                # Let's INSPECT it
                print(f"🕵️ Browser Attributes: {dir(browser)}")
                
                b_session_id = getattr(browser, 'session_id', None)
                print(f"🕵️ Extracted Session ID: {b_session_id}")
                
                if b_session_id:
                    session_url = f"https://cloud.browser-use.com/sessions/{b_session_id}"
                    print(f"🔗 Browser Use Session: {session_url}")
                    if session_id:
                         # BOLD and Highlighted as requested
                         link_msg = f"## 🔗 **Watch Live on Browser Use Cloud**: [**Click Here to View Agent**]({session_url})"
                         supabase_service.save_chat_message(session_id, "model", link_msg)
                         # BROADCAST to UI immediately
                         await log_stream_manager.broadcast(str(session_id), link_msg, type="log")
            except Exception as e:
                print(f"could not extract session url: {e}")
        else:
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
            
            if session_id:
                # Log status update to chat (debounced? or just log all major updates)
                supabase_service.save_chat_message(session_id, "model", f"🔄 {status}")

            return "Status updated"

            return "Status updated"

        # --- LOGGING SETUP ---
        log_handler = None
        if session_id:
            try:
                # Custom Handler to stream logs to frontend
                class BroadcastLogHandler(logging.Handler):
                    def __init__(self, s_id):
                        super().__init__()
                        self.session_id = str(s_id)
                    def emit(self, record):
                        try:
                            msg = self.format(record)
                            asyncio.create_task(log_stream_manager.broadcast(self.session_id, msg, type="log"))
                        except Exception:
                            self.handleError(record)

                log_handler = BroadcastLogHandler(session_id)
                formatter = logging.Formatter('%(levelname)s [%(name)s] %(message)s')
                log_handler.setFormatter(formatter)
                
                # Attach to browser_use logger
                logging.getLogger("browser_use").addHandler(log_handler)
                # Also attach to root/agent if needed, ensuring we don't duplicate too much
                # logging.getLogger().addHandler(log_handler) # Too noisy
            except Exception as e:
                print(f"⚠️ Failed to attach log handler: {e}")

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

            # --- IMPROVED JSON PARSING ---
            result_data = {}
            try:
                import re
                # 1. Try to find JSON inside markdown blocks ```json ... ```
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', result_str, re.DOTALL)
                
                # 2. If not found, try to find the first opening/closing brace pair
                if not json_match:
                     json_match = re.search(r'(\{.*\})', result_str, re.DOTALL)

                if json_match:
                    clean_json = json_match.group(1).strip()
                    result_data = json.loads(clean_json)
                else:
                    # If strictly no JSON found, assume it's raw text status (likely failure)
                    # But try to parse it as JSON one last time in case it is bare JSON
                    try:
                        result_data = json.loads(result_str.strip())
                    except json.JSONDecodeError:
                         # It is just plain text (e.g. "I failed because...")
                         pass

                status = result_data.get("status", "Unknown")
                account_created = result_data.get("account_created", False)
                final_url = result_data.get("final_url", resolved_url)

            except Exception as e:
                print(f"⚠️ Warning: Could not parse agent JSON result: {e}. Raw: {result_str}")
                # Fallback logic remains the same
                account_created = "ACCOUNT_CREATED" in str(history) 
                final_url = resolved_url
                status = result_str # Use raw string so the "FAILED" check below catches it

            # Extract Final Domain
            from urllib.parse import urlparse
            final_domain = urlparse(final_url).netloc

            # Save generated credentials if we created an account
            if getattr(result_data, 'get', lambda k: None)("status") == "APPLIED" or account_created:
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
            if log_handler:
                try:
                    logging.getLogger("browser_use").removeHandler(log_handler)
                except: pass
            
            try:
                # FIX: Wait for background tasks (CDP cleanup)
                await asyncio.sleep(2.0)
                if hasattr(browser, 'close'):
                    await browser.close()
            except Exception:
                pass
