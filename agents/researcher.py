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

        for query in queries:
            if len(all_leads) >= limit:
                break

            print(f"\n🔎 Searching: '{query}' in '{location}'")

            query_leads_count = 0

            # Pagination Loop: Try up to 5 pages
            for page in range(1, 6):
                if query_leads_count >= max_per_query:
                    print(f"   ✋ Reached reasonable depth for query '{query}'. Next.")
                    break

                if len(all_leads) >= limit:
                    break

                # 1. Construct URL
                encoded_q = urllib.parse.quote(query)
                encoded_l = urllib.parse.quote(location)
                url = f"https://www.getwork.com/search?q={encoded_q}&w={encoded_l}&page={page}"
                print(f"   Using URL (Page {page}): {url}")

                # 2. Browser Task
                task = (
                    f"1. Navigate to {url}\n"
                    f"2. Scroll down 3 times. Wait 2 seconds between scrolls.\n"
                    f"3. Look for the main list of job cards.\n"
                    f"4. CHECK for a 'Next' button.\n"
                    f"5. ITERATE through the job cards found.\n"
                    f"7. **CRITICAL**: IGNORE items marked as 'Sponsored', 'Ad'.\n"
                    f"8. If NO jobs are found, return exactly `{{ 'jobs': [], 'has_next_page': false }}`.\n"
                    f"9. Return: {{'jobs': [list of {{'title': str, 'company': str, 'url': str, 'snippet': str}}], 'has_next_page': bool}}"
                )

                browser = Browser(headless=True)
                try:
                    agent = Agent(task=task, llm=self.llm, browser=browser)
                    history = await agent.run()
                    raw_result = history.final_result()

                    if not raw_result:
                        break

                    try:
                        clean_result = raw_result.replace('```json', '').replace('```', '').strip()
                        data = json.loads(clean_result)
                        if isinstance(data, list):
                            batch_leads = data
                            has_next_page = False
                        else:
                            batch_leads = data.get('jobs', [])
                            has_next_page = data.get('has_next_page', False)
                    except Exception:
                        break

                    if not batch_leads:
                        break

                    print(f"   Found {len(batch_leads)} raw items.")

                    for lead in batch_leads:
                        # DEDUPLICATE RAW
                        title = lead.get('title', 'Unknown').strip()
                        company = lead.get('company', 'Unknown').strip()
                        signature = f"{company.lower()}|{title.lower()}"

                        if signature in self.seen_jobs:
                            continue

                        lead['query_source'] = query
                        all_leads.append(lead)
                        self.seen_jobs.add(signature)
                        query_leads_count += 1

                    if not has_next_page:
                        break

                except Exception as e:
                    print(f"   ❌ Error: {e}")
                finally:
                    try:
                        await browser.close()
                    except:
                        pass

                await asyncio.sleep(1)

        return all_leads
