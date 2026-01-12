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
        self.llm = ChatGoogle(model='gemini-2.5-flash', api_key=api_key)
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

    async def generate_strategy(self, profile: dict) -> List[str]:
        """
        Generates Google Search queries targeting specific ATS domains.
        """
        print("🧠 GoogleResearcher: Generating Verified ATS Search Strategy...")

        if not profile:
            return ["site:boards.greenhouse.io Software Engineer"]

        # We'll ask the LLM to just give us the Job Titles, then we wrap them in site: operators logic manually
        # This ensures we control the 'verification' part better.
        raw_text_snippet = profile.get('raw_text', '')[:1000] # Give context from raw text
        
        prompt = f"""
        Act as an expert Recruiter. Analyze this candidate profile:
        {json.dumps(profile, indent=2)}
        
        Raw Text Context:
        {raw_text_snippet}

        Task:
        1. Identify the candidate's core Role Name (e.g. "Software Engineer", "Product Manager"). Use STANDARDIZED industry titles, not niche internal ones.
        2. Identify their Level (Senior, Staff, Intern, etc).
        3. Generate 3 distinct, professional Job Titles they should target.
           - Rule: Combine Role + Level (e.g. "Software Engineer Intern", "Senior Backend Developer").
           - Rule: NEVER output single-word titles like "Intern", "Manager", "Analyst". Be specific.
           - Rule: If the candidate is a student/intern, include "Intern" or "Co-op" in the title (e.g. "Software Engineering Intern"), But be sure to check the date when they attended college.
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
                 # Filter out single-word titles (double safety)
                 if clean and ' ' in clean: 
                     cleaned_titles.append(clean)
                 elif clean:
                     # Check if it's a compound word or specialized?
                     # For now, simplistic check: if length > 1 word, keep.
                     if len(clean.split()) > 1:
                         cleaned_titles.append(clean)
            
            # Now combine with ATS domains to make robust queries
            # We don't want to make 5 titles * 6 domains = 30 queries. That's too many.
            # Strategy: Group domains or rotate them? 
            # Better: "site:greenhouse.io OR site:lever.co OR ... " (Google allows ~32 words)
            
            ats_group_1 = " OR ".join([f"site:{d}" for d in self.ats_domains[:3]])
            ats_group_2 = " OR ".join([f"site:{d}" for d in self.ats_domains[3:]])
            
            queries = []
            for title in cleaned_titles:
                # We'll search for the title + location is handled usually by the user or implicit?
                # Let's add location if it exists in profile
                loc = profile.get('location', '')
                
                # Query 1: Group A
                queries.append(f"({ats_group_1}) \"{title}\" {loc}")
                # Query 2: Group B
                queries.append(f"({ats_group_2}) \"{title}\" {loc}")
            
            # Shuffle and pick top X to avoid overload? 
            # For now, let's take up to 8 queries total
            random.shuffle(queries)
            return queries[:8]

        except Exception as e:
            print(f"⚠️ Strategy Generation Error: {e}")
            return [f"site:boards.greenhouse.io Software Engineer"]

    async def gather_leads(self, profile: dict, limit: int = 100, job_title: str = None, location: str = None) -> List[Dict[str, Any]]:
        """
        Executes Google Search queries to find direct ATS links.
        """
        queries = await self.generate_strategy(profile)
        
        # Override if manual title provided (for testing)
        if job_title:
             # Basic override logic
             ats_group = " OR ".join([f"site:{d}" for d in self.ats_domains])
             loc = location if location else profile.get('location', '')
             queries = [f"({ats_group}) \"{job_title}\" {loc}"]

        all_leads = []
        max_per_query = math.ceil(limit / max(len(queries), 1)) + 2

        # Parallel Execution
        concurrency = 1
        semaphore = asyncio.Semaphore(concurrency)
        


        try:
            async def process_query(query: str):
                async with semaphore:
                    if len(all_leads) >= limit: return []
                    
                    print(f"🔎 Brave Search: '{query}'")
                    query_leads = []
                    
                    try:
                        # Construct Direct URL (Using Brave Search)
                        encoded_q = urllib.parse.quote(query)
                        # Request specific URL to avoid redirects/tracking
                        url = f"https://search.brave.com/search?q={encoded_q}" 

                        # We instruct the agent to use Brave Search
                        task_prompt = (
                            f"Go to {url} . "
                            f"Extract the TOP 5 search results. "
                            f"For each result, try to parse the 'Company' from the title or URL. "
                            f"Return a strict JSON object: {{'jobs': [{{'title': '...', 'company': '...', 'url': '...', 'snippet': '...'}}]}}. "
                            f"Keep snippets short (max 20 words). "
                            f"IMPORTANT: If the page fails to load, shows a CAPTCHA, or times out, RETURN EMPTY JSON {{'jobs': []}} IMMEDIATELY. DO NOT ATTEMPT TO SEARCH AGAIN."
                        )
                        
                        # Add random delay to be a good citizen
                        await asyncio.sleep(random.uniform(1.0, 3.0))

                        # Create a fresh browser instance for each query to ensure reliability
                        # Configure browser with stealth args and timeout
                        browser = Browser(
                            headless=True,
                            disable_security=True,
                            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                        )

                        try:
                            # Disable vision to speed up and avoid screenshot timeouts
                            agent = Agent(task=task_prompt, llm=self.llm, browser=browser, use_vision=False)
                            history = await agent.run()
                            
                            raw = history.final_result() or ""
                            
                            # Same JSON extraction logic as ResearcherAgent
                            # (Refactor this to a util later?)
                            json_blocks = re.findall(r'```json\s*(.*?)```', raw, re.DOTALL)
                            if not json_blocks:
                                 match = re.search(r'\{.*"jobs":\s*\[.*\]\s*\}', raw, re.DOTALL)
                                 if match: json_blocks = [match.group(0)]
                            
                            for block in json_blocks:
                                try:
                                    data = json.loads(block.strip())
                                    jobs = data.get('jobs', [])
                                    for j in jobs:
                                        # Validation: Must be from our ATS list?
                                        url = j.get('url', '')
                                        if any(d in url for d in self.ats_domains):
                                            query_leads.append({**j, 'is_direct_listing': True, 'query_source': query})
                                except:
                                    pass
                        finally:
                            if hasattr(browser, 'close'):
                                await browser.close()

                    except Exception as e:
                        print(f"   ❌ Error on {query}: {e}")
                    
                    return query_leads

            tasks = [process_query(q) for q in queries]
            results = await asyncio.gather(*tasks)

        except Exception as e:
            print(f"❌ Critical Error in Gather: {e}")
            results = []



        for res in results:
            for lead in res:
                # Deduplicate
                # Use URL as primary key for direct ATS links
                sig = lead.get('url', '').lower()
                if sig and sig not in self.seen_jobs:
                    self.seen_jobs.add(sig)
                    all_leads.append(lead)
        
        return all_leads[:limit]
