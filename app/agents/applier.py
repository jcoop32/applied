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
        Includes 'Redirect Chaser' logic to bypass aggregators.
        """
        print(f"🕵️ Resolving true application URL for: {job_url}")

        KNOWN_ATS = ["greenhouse.io", "lever.co", "workday.com", "ashbyhq.com", "bamboohr.com", "smartrecruiters.com", "icims.com"]
        KNOWN_AGGREGATORS = ["adzuna.com", "indeed.com", "linkedin.com", "ziprecruiter.com", "glassdoor.com"]

        try:
            # 1. Fetch RAW HTML
            def fetch_raw():
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                }
                response = requests.get(job_url, headers=headers, timeout=10, allow_redirects=True)
                return response.text, response.url

            html_content, final_url = await asyncio.to_thread(fetch_raw)

            # 2. Ask the LLM to find the link using RAW content
            client = genai.Client(api_key=self.api_key)

            prompt = f"""
            I have the raw HTML content of a job posting page below.
            Find the URL for the "Apply", "Apply Now", "Apply on Company Site", or "Start Application" button.

            rules:
            1. Return ONLY the raw URL. No JSON, no text, no markdown.
            2. PRIORITIZE links to external generic ATS platforms: {', '.join(KNOWN_ATS)}.
            3. AVOID links to other aggregators if possible: {', '.join(KNOWN_AGGREGATORS)}.
            4. If the only link is an aggregator (e.g. Adzuna), return it, but try to find the button that says "Go to company site" or "Apply on Employer Site".
            5. If the URL is relative (starts with /), append it to the base domain: {final_url}
            6. If the page shows "Access Denied", "Security Check", or similar blockage, look for ANY link that contains "redirect", "click", "authenticate", or the job ID, which might bypass the block.

            HTML Content (Truncated if too large):
            {html_content[:100000]}
            """

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )

            extracted_text = (response.text or "").strip()
            
            # Regex to find the first URL in case LLM chats
            import re
            url_match = re.search(r'https?://[^\s<>"]+|www\.[^\s<>"]+', extracted_text)
            if url_match:
                extracted_url = url_match.group(0)
            else:
                extracted_url = extracted_text

            # Basic validation
            if extracted_url and "http" in extracted_url:
                print(f"🤖 LLM identified Apply URL: {extracted_url}")
                
                # --- REDIRECT CHASER LOGIC ---
                # If the URL looks like an aggregator, try to resolve the final destination via HEAD/GET
                from urllib.parse import urlparse
                domain = urlparse(extracted_url).netloc
                
                if any(agg in domain for agg in KNOWN_AGGREGATORS):
                    print(f"⚠️ Detected Aggregator URL ({domain}). Attempting to follow redirects...")
                    
                    async def follow_redirects(url):
                        headers = {
                             # Mimic a real browser to pass basic checks 
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                        try:
                            # 1. Standard Redirect Follow (Sync in thread or direct)
                            # Since we are now async, we can use a thread for requests, or just use requests directly if we accept blocking (but better to thread it)
                            loop = asyncio.get_event_loop()
                            r = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers, allow_redirects=True, timeout=15))
                            final_url = r.url
                            
                            # 2. Soft Redirect / Block Page Check
                            # Adzuna often returns 200/403 with a 'Link to continue' or '/authenticate' hidden link
                            if "adzuna" in final_url or "Access Denied" in r.text or "Security Check" in r.text or "authenticate" in r.text:
                                import re
                                # Look for /authenticate links or any redirect_to param
                                auth_match = re.search(r'href=["\'](/?authenticate[^"\']+)["\']', r.text)
                                if auth_match:
                                    # Construct absolute URL
                                    rel_link = auth_match.group(1)
                                    final_auth_link = f"https://www.adzuna.com{rel_link}" if rel_link.startswith("/") else rel_link
                                    return await self._resolve_url_with_browser(final_auth_link)
                                
                                # Look for generic window.location redirects
                                js_match = re.search(r'window\.location\s*=\s*["\']([^"\']+)["\']', r.text)
                                if js_match:
                                    return await self._resolve_url_with_browser(js_match.group(1))
                                    
                            # If we are still on aggregator, try browser fallback
                            if any(agg in final_url for agg in KNOWN_AGGREGATORS):
                                print(f"⚠️ Still on aggregator ({final_url}). Switching to Browser Resolution...")
                                return await self._resolve_url_with_browser(final_url)

                            return final_url
                            
                        except Exception as e:
                            print(f"⚠️ Redirect check failed: {e}")
                        return url

                    final_dest = await follow_redirects(extracted_url)
                    
                    if final_dest != extracted_url:
                        print(f"🎯 Redirect Chaser resolved: {extracted_url} -> {final_dest}")
                        extracted_url = final_dest
                    else:
                        print(f"⚠️ Could not resolve redirect or URL is unchanged.")

                # FINAL VALIDATION: Ensure we are not returning an aggregator
                from urllib.parse import urlparse
                final_domain = urlparse(extracted_url).netloc
                if any(agg in final_domain for agg in KNOWN_AGGREGATORS):
                    print(f"❌ Failed to resolve URL. Stuck on aggregator: {final_domain}")
                    # The user explicitly said: "resolved url should never be adzuna"
                    # We raise an error or return the original job_url (which might be GetWork, better than Adzuna?)
                    # But GetWork is also not an ATS. 
                    # Let's return the extracted_url but log a CRITICAL warning, OR raise an error.
                    # Best approach: Raise error to stop the agent from wasting money applying to Adzuna.
                    raise ValueError(f"Could not bypass aggregator ({final_domain}). Manual intervention required.")

                return extracted_url

            print(f"⚠️ LLM could not find URL in HTML: {extracted_url}")
            return final_url # Fallback to current

        except Exception as e:
            print(f"⚠️ Resolution failed: {e}")
            import traceback
            traceback.print_exc()
            # If we explicitly raised ValueError, re-raise it to stop the process
            if isinstance(e, ValueError):
                raise e
            return job_url

    async def _resolve_url_with_browser(self, url: str) -> str:
        """
        Uses a lightweight headless browser to follow JS redirects.
        If it gets stuck on an aggregator page (like Adzuna Login), it scans the DOM for the target link.
        """
        print(f"🌐 Browser Resolver: navigating to {url}")
        from playwright.async_api import async_playwright
        
        KNOWN_ATS = ["greenhouse.io", "lever.co", "workday.com", "ashbyhq.com", "bamboohr.com", "smartrecruiters.com", "icims.com"]
        
        try:
            async with async_playwright() as p:
                # Use self.headless to allow debug if configured
                # Add stealth args to avoid basic bot detection
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-infobars"]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    locale="en-US"
                )
                page = await context.new_page()
                
                # Set robust headers (though context handles UA)
                await page.set_extra_http_headers({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9"
                })
                
                try:
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    # Wait for JS redirects or 'Click here' to process
                    await page.wait_for_timeout(10000)
                    
                    final_url = page.url
                    print(f"🌐 Browser Resolver landed on: {final_url}")
                    
                    # If we are effectively resolved to a non-aggregator, return it
                    if not any(agg in final_url for agg in ["adzuna.com", "indeed.com", "linkedin.com"]):
                         return final_url

                    # FALLBACK: If we are stuck on Adzuna (Login/Block), scan the page for the real link
                    print("⚠️ Still on aggregator. Scanning page content for hidden ATS links...")
                    content = await page.content()
                    
                    import re
                    # 1. Try Regex Scan first (Fast)
                    for ats in KNOWN_ATS:
                        match = re.search(r'https?://[^"\'\s>]*' + re.escape(ats) + r'[^"\'\s>]*', content)
                        if match:
                            found_url = match.group(0)
                            print(f"🎯 Found hidden ATS link in DOM (Regex): {found_url}")
                            return found_url

                    # 2. Try LLM Scan (Smart)
                    print("🧠 Asking LLM to find the redirect/ATS link in the blocked page...")
                    
                    # Truncate content for LLM
                    truncated_content = content[:50000] 
                    prompt = f"""
                    I am stuck on a job aggregator page (Adzuna) that failed to redirect.
                    Analyze the HTML below and find the DIRECT link to the applicant tracking system (ATS) or the employer's site.
                    Look for hidden URLs, 'window.location', 'meta refresh', or simple 'Click here' links.
                    
                    Prioritize domains like: {', '.join(KNOWN_ATS)}
                    
                    HTML:
                    {truncated_content}
                    
                    Rules:
                    1. Return ONLY the URL.
                    2. If not found, return 'NOT_FOUND'.
                    """
                    
                    # Use raw client for consistency
                    client = genai.Client(api_key=self.api_key)
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model='gemini-2.5-flash',
                        contents=prompt
                    )
                    llm_url = (response.text or "").strip()
                    
                    # Clean up
                    url_match = re.search(r'https?://[^\s<>"]+|www\.[^\s<>"]+', llm_url)
                    if url_match:
                         clean_url = url_match.group(0)
                         # Basic sanity check
                         if "adzuna" not in clean_url and "http" in clean_url:
                             print(f"🎯 LLM found hidden link: {clean_url}")
                             return clean_url
                            
                    return final_url
                    
                except Exception as nav_e:
                     print(f"⚠️ Browser navigation error: {nav_e}")
                     return url
                finally:
                    await browser.close()
        except Exception as e:
            print(f"⚠️ Browser Resolver failed: {e}")
            return url

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

        # 7. Voluntary Disclosures (OPTIONAL):
        #    - *Instructions*: These fields are often hidden or effectively optional. 
        #    - **CRITICAL**: If you cannot easily find 'Veteran' or 'Disability' sections, OR if interacting with them fails after 1 attempt, **SKIP THEM**.
        #    - Do NOT get stuck trying to scroll/find these specific fields.
        #    - If present:
        #      - Gender: `{profile.get('Voluntary Questions Answers', {}).get('Gender', 'Decline to identify')}`
        #      - Race: `{profile.get('Voluntary Questions Answers', {}).get('Race', 'Decline to identify')}`
        #      - Veteran: `{profile.get('Voluntary Questions Answers', {}).get('Veteran Status', 'No')}`
        #      - Disability: `{profile.get('Voluntary Questions Answers', {}).get('Disability Status', 'No')}`

        # 8. Submission & Validation:
        #    - **LOOP (Max 3 attempts)**:
        #      1. **Hover** over "Submit"/"Apply" for 1s.
        #      2. **CRITICAL PRE-SUBMIT CHECK**: Scour the page for "I Agree" / "Terms" checkboxes again. Click them if unchecked.
        #      3. Click "Submit".
        #      4. **WAIT 3 SECONDS**.
        #      5. **SCAN FOR ERRORS**: Look for red text, "Required field", or "Invalid".
        #      6. **IF ERRORS**: **FIX THEM**. Focus on the empty required fields. REPEAT.
        #      7. **IF SUCCESS**: Stop.

        # 9. Output:
        #    - Return JSON: `{{ "status": "<Submitted/DryRun/Failed>", "account_created": <true/false>, "final_url": "<url>" }}`
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
            result_data = {} # Initialize default
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
                status = result_str # Use raw string as status

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
            try:
                if hasattr(browser, 'close'):
                    await browser.close()
            except Exception:
                pass
