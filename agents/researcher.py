import json
import asyncio
import re
from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch

class ResearcherAgent:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.0-flash"

    async def gather_leads(self, profile_data, target_count=10):
        print(f"🧠 Researcher Agent started. Target: {target_count} jobs...")

        # 1. STRATEGY PHASE (Restored the prompt you liked)
        strategy_prompt = f"""
        Act as an expert Technical Recruiter. Analyze this candidate profile:
        {json.dumps(profile_data, indent=2)}

        Task:
        1. Determine the candidate's exact Seniority Level.
        2. Generate 4-5 specific Google Search Queries to find DIRECT job application pages.

        CRITICAL RULES:
        - Use boolean operators: site:greenhouse.io OR site:lever.co OR site:workday.com
        - Focus on: Job Title + Location + "Apply"
        - Example: "Senior Python Developer" (site:greenhouse.io OR site:lever.co) "Chicago"

        Output ONLY the list of queries.
        """

        strategy_resp = self.client.models.generate_content(
            model=self.model_id,
            contents=strategy_prompt
        )
        print(f"📝 Search Strategy:\n{strategy_resp.text}\n")

        # --- STEP 2: SEARCH LOOP ---
        found_leads = {}
        attempts = 0

        while len(found_leads) < target_count and attempts < 6:
            attempts += 1
            needed = target_count - len(found_leads)
            print(f"🔎 Round {attempts}: Hunting for {needed} links...")

            search_prompt = f"""
            Refer to this strategy:
            {strategy_resp.text}

            Execute a new Google Search to find {needed} NEW, ACTIVE job postings.

            CRITICAL INSTRUCTION:
            After searching, you MUST **list the Direct URLs** found in the search results explicitly in your text response.
            Do not hide them in markdown links. Write the raw URL (e.g., https://boards.greenhouse.io/...).
            """

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=search_prompt,
                config=GenerateContentConfig(
                    tools=[Tool(google_search=GoogleSearch())],
                    response_mime_type="text/plain"
                )
            )

            # --- STEP 3: LINK EXTRACTION (Clean Links Only) ---
            potential_links = set()

            # A. Metadata Extraction (Filtered)
            raw_meta_links = self._extract_links_from_grounding(response)
            for link in raw_meta_links:
                if "vertexaisearch" not in link and "google.com" not in link:
                    potential_links.add(link)

            # B. Regex Extraction (The Primary Source now)
            # We explicitly asked the model to write the URLs, so regex should catch them.
            text_links = re.findall(r'https?://[^\s)"]+', response.text)
            for link in text_links:
                clean_link = link.rstrip('.').rstrip(',').rstrip(';').rstrip(')').rstrip(']')
                # Filter out the junk redirects here too
                if "vertexaisearch" not in clean_link and "google.com" not in clean_link:
                    potential_links.add(clean_link)

            print(f"   - Clean links found: {len(potential_links)}")
            if len(potential_links) > 0:
                print(f"     Sample: {list(potential_links)[:2]}")

            if not potential_links:
                print("   ⚠️ No clean links found. Retrying...")
                continue

            # --- STEP 4: VALIDATION ---
            validation_prompt = f"""
            I have a list of raw URLs. Select the ones that are likely **Job Postings**.

            SEARCH STRATEGY:
            {strategy_resp.text}

            RAW URLS:
            {json.dumps(list(potential_links), indent=2)}

            INSTRUCTIONS:
            - Select ANY URL that looks like a direct job description or application page.
            - **BE PERMISSIVE:** If it is a greenhouse.io, lever.co, or workday link, ALWAYS accept it.
            - IGNORE general "Careers" home pages.

            Return a JSON list.
            Format: [{{"title": "Infer from URL/Context", "company": "Infer from URL", "url": "THE_EXACT_URL"}}]
            """

            batch_leads = []
            try:
                json_resp = self.client.models.generate_content(
                    model=self.model_id,
                    contents=validation_prompt
                )

                cleaned_json = self._clean_json_string(json_resp.text)
                batch_leads = json.loads(cleaned_json)
                print(f"   - Validator accepted: {len(batch_leads)} links")

            except Exception as e:
                print(f"   ⚠️ Validator Issue: {e}. Switching to Manual Rescue.")
                batch_leads = []

            # --- STEP 5: SAFETY NET (Manual Rescue) ---
            if not batch_leads and len(potential_links) > 0:
                print("   🛡️ Engaging Safety Net...")
                ats_domains = ["greenhouse.io", "lever.co", "workday", "ashby", "breezy.hr", "smartrecruiters", "jobvite", "icims"]
                url_keywords = ["/jobs/", "/careers/", "/position/", "/apply", "view-job", "job-detail"]

                for url in potential_links:
                    url_lower = url.lower()
                    is_ats = any(d in url_lower for d in ats_domains)
                    is_job_pattern = any(k in url_lower for k in url_keywords)

                    if (is_ats or is_job_pattern) and len(url) > 25:
                         batch_leads.append({
                             "title": "Detected by Safety Net",
                             "company": "Unknown",
                             "url": url
                         })
                         print(f"     -> Rescued: {url}")

            # Add to main list
            for job in batch_leads:
                url = job.get('url', '').strip()
                if len(url) < 15: continue

                if url and url not in found_leads:
                    found_leads[url] = job
                    print(f"   + Added: {job.get('company', 'Job')} - {job.get('title', 'Unknown')}")

            await asyncio.sleep(2)

        return list(found_leads.values())

    def _extract_links_from_grounding(self, response):
        """Extracts verified URLs from the Google Search metadata."""
        links = set()
        try:
            for candidate in response.candidates:
                if candidate.grounding_metadata and candidate.grounding_metadata.grounding_chunks:
                    for chunk in candidate.grounding_metadata.grounding_chunks:
                        if chunk.web and chunk.web.uri:
                            links.add(chunk.web.uri)
        except Exception:
            pass
        return list(links)

    def _clean_json_string(self, json_str):
        if not json_str: return "[]"
        cleaned = re.sub(r'^```json\s*', '', json_str, flags=re.MULTILINE)
        cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()
        if not cleaned: return "[]"
        return cleaned
