import json
import asyncio
import urllib.parse
import re
import math
import random
from typing import List, Set, Dict, Any
from google import genai
from browser_use import Agent, Browser
from browser_use.llm import ChatGoogle

class GoogleResearcherAgent:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.api_key = api_key
        self.model_id = 'gemini-2.5-flash'
        # Try to pass max_output_tokens directly if supported, otherwise rely on defaults or model_kwargs
        # Common Langchain wrapper accepts max_output_tokens
        self.llm = ChatGoogle(model='gemini-2.5-flash', api_key=api_key, max_output_tokens=8192)
        self.seen_jobs: Set[str] = set()
        
        # Valid ATS Domains to target for "Verified" jobs
        self.ats_domains = [
            "boards.greenhouse.io",
            "jobs.lever.co",
            "myworkdayjobs.com",
            "jobs.ashbyhq.com",
            "jobs.jobvite.com", 
            "careers.smartrecruiters.com"
        ]

        # Suppress verbose browser-use logs
        import logging
        logging.getLogger("browser_use").setLevel(logging.WARNING)

    async def _generate_titles(self, profile: dict) -> List[str]:
        """
        Generates professional job titles based on the candidate profile.
        """
        print("🧠 GoogleResearcher: Analyzing profile for target Job Titles...")

        if not profile:
            return ["Software Engineer"]

        raw_text_snippet = profile.get('raw_text', '')[:1000]
        
        prompt = f"""
        Act as an expert Recruiter. Analyze this candidate profile:
        {json.dumps(profile, indent=2)}
        
        Raw Text Context:
        {raw_text_snippet}

        Task:
        1. Identify the candidate's core Role Name (e.g. "Software Engineer", "Product Manager").
        2. Identify their Level (Senior, Staff, Intern, etc).
        3. Generate 3-5 distinct, professional Job Titles they should target.
           - Rule: Combine Role + Level (e.g. "Software Engineer Intern", "Senior Backend Developer").
           - Rule: NEVER output single-word titles like "Intern", "Manager", "Analyst". Be specific.
           - Rule: If the candidate is a student/intern, include "Intern" or "Co-op".
        4. Titles must be concise (max 4 words).
        
        Output ONLY a JSON list of strings (e.g. ["Senior Software Engineer", "Backend Developer"]).
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            titles = json.loads(response.text)
            
            # Clean titles
            cleaned_titles = []
            for t in titles:
                 clean = re.sub(r'[()\"\'\[\]]', '', t).strip()
                 if clean and ' ' in clean: 
                     cleaned_titles.append(clean)
                 elif clean and len(clean.split()) > 1:
                     cleaned_titles.append(clean)
            
            return cleaned_titles[:6] # Limit to top 6

        except Exception as e:
            print(f"⚠️ Strategy Generation Error: {e}")
            return ["Software Engineer"]

    async def gather_leads(self, profile: dict, limit: int = 15, job_title: str = None, location: str = None, should_stop_callback=None, log_callback=None) -> List[Dict[str, Any]]:
        """
        Executes Google Search queries to find direct ATS links.
        Loops through search strategies until 'limit' is reached or options exhausted.
        """
        # 1. Get Target Titles
        if job_title:
            titles = [job_title]
        else:
            titles = await self._generate_titles(profile)

        # 2. Setup Loop
        all_leads = []
        # We want to fill 'limit' unique leads.
        # Strategies:
        # Phase A (Attempt 0): Stricter, quoted searches. "Title" site:ats
        # Phase B (Attempt 1): Broader, unquoted searches. Title site:ats
        
        user_loc = location if location else profile.get('location', '')
        
        # Split domains into chunks to avoid query length limits
        # Google limit is around 32 words.
        chunk_size = 3
        domain_chunks = [self.ats_domains[i:i + chunk_size] for i in range(0, len(self.ats_domains), chunk_size)]

        max_attempts = 2 # 0: Strict, 1: Broad
        
        for attempt in range(max_attempts):
            # Check if we have enough leads
            if len(all_leads) >= limit:
                break
                
            is_strict = (attempt == 0)
            phase_name = "Strict" if is_strict else "Broad"
            
            print(f"🔄 Search Phase {attempt+1}/{max_attempts} ({phase_name}): Target {limit} leads (Have {len(all_leads)})")
            if log_callback: await log_callback(f"Phase {attempt+1}: {phase_name} search for {len(titles)} titles...")

            # Generate Queries for this phase
            queries = []
            for t in titles:
                # If strict, quote the title
                t_str = f'"{t}"' if is_strict else t
                
                for d_chunk in domain_chunks:
                    site_op = " OR ".join([f"site:{d}" for d in d_chunk])
                    q = f"({site_op}) {t_str} {user_loc}"
                    queries.append(q)

            # Shuffle queries to avoid hitting same domains sequentially?
            # Actually, better to interleave titles.
            random.shuffle(queries)
            
            # If we are in broad mode, we might want to cap queries to avoid infinite spam
            # But "until limit" is the goal.
            # Let's slice queries if too many?
            # If we requested 3 matches, and we have 5 titles * 2 chunks = 10 queries.
            # If we run all 10 concurrent-ish, it's fast.
            
            # Execute Batch
            # Reuse process_query logic (inline or helper?)
            # Refactoring process_query to method could be cleaner, but inline preserves closure context easily.
            
            # Run the batch
            batch_leads = await self._execute_search_batch(queries, limit - len(all_leads), should_stop_callback, log_callback)
            
            # Add to all_leads (deduplication happens in _execute_search_batch or here?)
            # Let's dedupe here against global seen_jobs
            new_count = 0
            for lead in batch_leads:
                sig = lead.get('url', '').lower()
                if sig and sig not in self.seen_jobs:
                    self.seen_jobs.add(sig)
                    all_leads.append(lead)
                    new_count += 1
            
            print(f"   found {new_count} new unique leads in this phase.")
            
            if len(all_leads) >= limit:
                 print("✅ Limit reached.")
                 break
            
            if should_stop_callback and await should_stop_callback():
                break

        return all_leads[:limit]

    async def _execute_search_batch(self, queries: List[str], needed: int, should_stop_callback, log_callback) -> List[Dict]:
        """
        Helper to run a batch of queries concurrently.
        """
        batch_results = []
        if needed <= 0: return []

        concurrency = 1 # Keep 1 for stability/evasion
        semaphore = asyncio.Semaphore(concurrency)
        
        browser_user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

        async def process_query(query: str):
             async with semaphore:
                 if should_stop_callback and await should_stop_callback(): return []
                 # Fast exit if we (theoretically) filled the batch in another task? 
                 # Hard to sync without mutex, but 'needed' is rough guidance.
                 
                 msg = f"🔎 Brave Search: '{query}'"
                 print(msg)
                 # Only log verbose if needed
                 # if log_callback: await log_callback(msg)

                 query_leads = []
                 try:
                     encoded_q = urllib.parse.quote(query)
                     url = f"https://search.brave.com/search?q={encoded_q}&source=web"
                     
                     # Task Prompt (Same as before)
                     task_prompt = (
                        f"Go to {url} . "
                        f"Extract the TOP 5 search results directly into JSON. "
                        f"CRITICAL: Extract the EXACT 'href' from the link. "
                        f"Return strict JSON: {{'jobs': [{{'title': '...', 'company': '...', 'url': '...', 'snippet': '...'}}]}}. "
                        f"Constraint: Snippets < 20 words. No HTML. No Reasoning. "
                        f"Ignore 'page readiness' warnings."
                     )
                     
                     await asyncio.sleep(random.uniform(1.0, 2.0))
                     
                     if should_stop_callback and await should_stop_callback(): return []

                     # Fresh Browser
                     browser = Browser(
                         headless=True,
                         disable_security=True,
                         args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                         user_agent=browser_user_agent,
                         wait_for_network_idle_page_load_time=4.0,
                         minimum_wait_page_load_time=2.0 
                     )
                     
                     try:
                         agent = Agent(task=task_prompt, llm=self.llm, browser=browser, use_vision=False)
                         
                         agent_task = asyncio.create_task(agent.run())
                         
                         # Monitor cancellation 
                         while not agent_task.done():
                             if should_stop_callback and await should_stop_callback():
                                 agent_task.cancel()
                                 try: await agent_task 
                                 except: pass
                                 return []
                             await asyncio.sleep(0.5)
                         
                         history = await agent_task
                         raw = history.final_result() or ""
                         
                         # Extraction
                         json_blocks = re.findall(r'```json\s*(.*?)```', raw, re.DOTALL)
                         if not json_blocks:
                              match = re.search(r'\{.*"jobs":\s*\[.*\]\s*\}', raw, re.DOTALL)
                              if match: json_blocks = [match.group(0)]
                         
                         for block in json_blocks:
                             try:
                                 data = json.loads(block.strip())
                                 jobs = data.get('jobs', [])
                                 for j in jobs:
                                     url = j.get('url', '')
                                     if any(d in url for d in self.ats_domains):
                                         if await self._verify_url(url):
                                             query_leads.append({**j, 'is_direct_listing': True, 'query_source': query})
                             except: pass
                     finally:
                         if hasattr(browser, 'close'): await browser.close()

                 except Exception as e:
                     print(f"Error query {query}: {e}")
                 
                 return query_leads

        tasks = [process_query(q) for q in queries]
        results = await asyncio.gather(*tasks)
        
        flat = []
        for r in results: flat.extend(r)
        return flat

    async def _verify_url(self, url: str) -> bool:
        """
        Verifies if a URL is valid and accessible (200 OK) AND looks like an open job.
        Uses a lightweight HTML snippet check + LLM to detect "Job Closed" banners.
        """
        import requests
        try:
            # We run this in a thread to avoid blocking the async event loop
            def check():
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                }
                
                # 1. Fetch First 15KB Only (BLOCKING IO in Thread)
                try:
                    # stream=True allows us to read only a chunk
                    with requests.get(url, headers=headers, timeout=5, allow_redirects=True, stream=True) as response:
                        if response.status_code >= 400:
                            return False
                        
                        # Read first 15KB
                        chunk = next(response.iter_content(chunk_size=15000), b"")
                        html_snippet = chunk.decode('utf-8', errors='ignore')
                        
                        # Basic URL Check
                        if "error" in response.url.lower() or "not found" in response.url.lower():
                            return False

                except Exception as req_e:
                    # Connection failed completely
                    return False

                # 2. Fast LLM Check (Gemini Flash)
                # We ask if the job is OPEN based on the snippet
                snippet_prompt = f"""
                Analyze this HTML snippet from a job board.
                Is this job OPEN and accepting applications? 
                
                Return FALSE if:
                - It says "Job Closed", "Position Filled", "No longer accepting applications".
                - It is a generic login page not specific to a job.
                - It is a 404 block.

                HTML Snippet:
                {html_snippet[:10000]}

                Return JSON: {{ "is_valid_job": boolean }}
                """
                
                try:
                    # Synchronous Multimodal Call (Safe inside this to_thread wrapper)
                    response = self.client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=snippet_prompt,
                        config={
                             'response_mime_type': 'application/json',
                             'response_schema': {"type": "OBJECT", "properties": {"is_valid_job": {"type": "BOOLEAN"}}}
                        }
                    )
                    data = json.loads(response.text)
                    return data.get("is_valid_job", False)
                
                except Exception as llm_e:
                    print(f"⚠️ Verification LLM failed: {llm_e}")
                    # Fallback to simple keyword check
                    lower_html = html_snippet.lower()
                    if "closed" in lower_html or "filled" in lower_html:
                        return False
                    return True

            # CRITICAL: Wrap strict blocking IO and Sync LLM call in a thread
            return await asyncio.to_thread(check)
        except Exception:
            return False
