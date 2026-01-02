import json
import asyncio
import urllib.parse
import re
import math
from typing import List, Set, Dict, Any, Tuple
from google import genai
from browser_use import Agent, Browser
from browser_use.llm import ChatGoogle

class ResearcherAgent:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.api_key = api_key
        self.model_id = 'gemini-2.5-flash'
        # We instantiate the LLM here, but Browser is managed per-task
        self.llm = ChatGoogle(model='gemini-2.5-flash', api_key=api_key)
        self.seen_jobs: Set[str] = set() # Hash set for deduplication

        # Suppress verbose browser-use logs
        import logging
        logging.getLogger("browser_use").setLevel(logging.WARNING)

    async def generate_strategy(self, profile: dict) -> List[str]:
        """
        Analyzes the resume to generate a list of targeted search queries.
        Returns a list of strings like "Software Engineer" or "React Developer".
        """
        print("🧠 Researcher: Generating Search Strategy from profile...")

        # Simple fallback if profile is empty
        if not profile:
            return ["Software Engineer"]

        prompt = f"""
        Act as an expert Recruiter for ANY industry (Tech, Finance, Healthcare, Arts, etc.).
        Analyze this candidate profile:
        {json.dumps(profile, indent=2)}

        Task:
        1. Identify the candidate's **Primary Industry** and **Experience Level** (Intern, Entry Level, Junior, Mid-Level, Senior, Exec).
        2. Identify standard job titles for *their* specific level in *their* field.
        3. Generate 8 distinct search queries.
        4. **CRITICAL**: Generate CORE job titles strictly.
           - **REMOVE seniority terms**: Do NOT include words like "Junior", "Senior", "Entry Level", "Lead", "Manager" in the query.
           - **BAD**: "Junior Software Engineer", "Senior Marketing Manager"
           - **GOOD**: "Software Engineer", "Marketing Manager", "Account Executive"
           - We want to see ALL jobs for this role; the agent will filter them later.
           - Keep queries BROAD (max 2-4 words).
           - **CRITICAL**: Double check spelling of all terms (e.g. 'Engineer', not 'Engiineer'). Ensure professional accuracy.

        Output ONLY a JSON list of strings (the queries).
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            queries = json.loads(response.text)

            # Clean queries just in case
            cleaned_queries = []
            for q in queries:
                # Remove special chars like (), "", OR, AND
                clean = re.sub(r'[()\"\'\[\]]', '', q)
                clean = clean.replace(' OR ', ' ').replace(' AND ', ' ')
                cleaned_queries.append(clean.strip())
            return cleaned_queries

        except Exception as e:
            print(f"⚠️ Strategy Generation Error: {e}")
            return ["Entry Level Job", "Remote Job"]

    async def gather_leads(self, profile: dict, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Raw Scraper: Finds as many jobs as possible for the Matcher to score.
        Does NOT verify or filter (that is the Matcher's job).
        """
        queries = await self.generate_strategy(profile)
        location = profile.get('location', 'Remote')

        all_leads = []
        # We want broad coverage, so we don't strictly limit per query.
        # But we don't want to spend forever on one query if we have 8 queries.
        # Let's say we want ~15 raw leads per query to hit the total goal.
        max_per_query = math.ceil(limit / len(queries)) * 2 # Buffer

        # Parallel Execution Configuration
        # We want to run queries in parallel, but limit concurrency to avoid crushing the browser/system.
        concurrency = 3 # 3 parallel browsers is usually safe for a standard machine
        semaphore = asyncio.Semaphore(concurrency)

        async def process_query(query: str):
            async with semaphore:
                if len(all_leads) >= limit: return []

                print(f"🔎 Parallel Search: '{query}'")
                query_leads = []

                # Using 1-2 pages depth per query for speed, since we are running parallel
                for page in range(1, 3):
                    if len(all_leads) + len(query_leads) >= limit: break

                    encoded_q = urllib.parse.quote(query)
                    encoded_l = urllib.parse.quote(location)
                    url = f"https://www.getwork.com/search?q={encoded_q}&w={encoded_l}&page={page}"

                    browser = Browser(headless=True)
                    try:
                        task_prompt = (
                            f"Go to {url}. Scroll down twice to load more results. "
                            f"Extract ALL job cards visible. "
                            f"Return a strict JSON object with a 'jobs' key containing the list: "
                            f"{{'jobs': [{{'title': '...', 'company': '...', 'url': '...', 'snippet': '...'}}]}}. "
                            f"Do NOT save to a file. Return the JSON directly in the final result."
                        )
                        agent = Agent(task=task_prompt, llm=self.llm, browser=browser)
                        history = await agent.run()

                        # Logic: Extract JSON from Markdown blocks (handled multiple blocks)
                        raw = history.final_result() or ""

                        # Find all JSON blocks
                        # Note: The agent might return one big block or multiple small ones
                        json_blocks = re.findall(r'```json\s*(.*?)```', raw, re.DOTALL)

                        # Fallback: If no markdown blocks, try to find the raw JSON object
                        if not json_blocks:
                            # Try to find { "jobs": ... } patterns
                            match = re.search(r'\{.*"jobs":\s*\[.*\]\s*\}', raw, re.DOTALL)
                            if match:
                                json_blocks = [match.group(0)]

                        for block in json_blocks:
                            try:
                                data = json.loads(block.strip())
                                jobs = data.get('jobs', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

                                for j in jobs:
                                    if isinstance(j, dict):
                                        query_leads.append({**j, 'query_source': query})
                            except:
                                # Try a more lenient fix for "concatenated" JSON within a block?
                                # For now, just skip bad blocks
                                pass

                    except Exception as e:
                        print(f"   ❌ Error on {query} pg{page}: {e}")
                    finally:
                        try:
                            await browser.close()
                        except:
                            pass

                return query_leads

        # Run all queries
        tasks = [process_query(q) for q in queries]
        results = await asyncio.gather(*tasks)

        # Flatten results
        for res in results:
            for lead in res:
                # Deduplicate
                sig = f"{lead.get('company','').lower()}|{lead.get('title','').lower()}"
                if sig not in self.seen_jobs:
                    self.seen_jobs.add(sig)
                    all_leads.append(lead)
                    if len(all_leads) >= limit: break
            if len(all_leads) >= limit: break

        return all_leads
