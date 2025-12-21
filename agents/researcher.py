import os
import json
import re
from google import genai

class ResearcherAgent:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.5-flash"

    async def gather_leads(self, profile_data, search_query_extra=""):
        skills = ", ".join(profile_data.get('skills', [])[:5])
        location = profile_data.get('location', 'Chicago, IL')

        # Define a strict schema for the job list
        job_list_schema = {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "company": {"type": "STRING"},
                    "url": {"type": "STRING"},
                    "source": {"type": "STRING"}
                },
                "required": ["title", "company", "url"]
            }
        }

        prompt = f"""
        I am a career assistant. Search Google for 10 active job postings.

        Candidate: Skills ({skills}), Location ({location}).
        Context: {search_query_extra}

        Search for roles on LinkedIn, Greenhouse.io, Lever.co, or Workday.
        Return the result ONLY as a valid JSON list. No preamble or markdown.
        """

        print(f"🔎 Scouting jobs for: {skills} in {location}...")

        response = self.client.models.generate_content(
            model=self.model_id,
            contents=prompt,
            config={
                'tools': [{'google_search': {}}],
                'response_mime_type': 'application/json',
                'response_schema': job_list_schema
            }
        )

        # CLEANING LOGIC: Remove markdown blocks if they exist
        clean_text = response.text.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r'^```json\s*|```$', '', clean_text, flags=re.MULTILINE)

        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            print(f"⚠️ Failed to parse JSON. Raw output: {clean_text[:100]}...")
            return []
