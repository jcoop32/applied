import os
import json
import re
from google import genai

class ResearcherAgent:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.0-flash"

    async def gather_leads(self, profile_data, search_query_extra=""):
        skills = ", ".join(profile_data.get('skills', [])[:3]) # Top 3 only for better focus
        location = profile_data.get('location', 'Chicago, IL')

        # We use 'Google Dorks' to find actual application pages
        search_query = (
            f'site:boards.greenhouse.io OR site:jobs.lever.co OR site:workday.com '
            f'"{skills}" "{location}" "apply" {search_query_extra}'
        )

        print(f"🔎 Power-Searching: {search_query}...")

        # STEP 1: Search (We don't ask for JSON here to avoid the 400 error)
        search_prompt = f"""
        I need a list of 10 current job openings from this search: {search_query}.
        For each job, extract the Title, Company Name, and the Direct URL.
        """

        search_response = self.client.models.generate_content(
            model=self.model_id,
            contents=search_prompt,
            config={'tools': [{'google_search': {}}]}
        )

        raw_results = search_response.text

        # Check if we actually got text back
        if not raw_results or len(raw_results) < 50:
            print("⚠️ Search returned very little data. Trying broader query...")
            return []

        # STEP 2: Force into JSON
        # We include the grounding URIs manually as a backup
        grounding_links = []
        try:
            metadata = search_response.candidates[0].grounding_metadata
            if metadata.grounding_chunks:
                for chunk in metadata.grounding_chunks:
                    if chunk.web and chunk.web.uri:
                        grounding_links.append(chunk.web.uri)
        except:
            pass

        format_prompt = f"""
        Extract every job lead from this text into a JSON list.
        TEXT: {raw_results}
        VERIFIED LINKS: {grounding_links}

        JSON Format: [{{"title": "", "company": "", "url": "", "source": ""}}]
        """

        json_response = self.client.models.generate_content(
            model=self.model_id,
            contents=format_prompt,
            config={'response_mime_type': 'application/json'}
        )

        return json.loads(json_response.text)
