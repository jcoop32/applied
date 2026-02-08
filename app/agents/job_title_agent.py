import json
import re
from typing import List
from google import genai


class JobTitleAgent:
    """
    Analyzes parsed resume data and generates up to 10 fitting job titles.
    Lightweight: uses Gemini Flash with structured JSON output, no browser needed.
    """

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Gemini API Key is required for JobTitleAgent.")
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.5-flash"

    async def generate_titles(self, profile_data: dict) -> List[str]:
        """
        Takes parsed resume/profile data and returns up to 10 professional job titles.
        Titles reflect the candidate's skills, experience level, and career trajectory.
        """
        if not profile_data:
            print("⚠️ JobTitleAgent: Empty profile data, returning defaults.")
            return ["Software Engineer"]

        # Build a rich context string from the profile
        skills = profile_data.get("skills", [])
        work_experience = profile_data.get("work_experience", [])
        education = profile_data.get("education", [])
        summary = profile_data.get("summary", "")
        raw_text = profile_data.get("raw_text", "")

        # Extract past job titles for context
        past_titles = [exp.get("title", "") for exp in work_experience if exp.get("title")]

        prompt = f"""
        Act as an expert Career Counselor and Recruiter. Analyze this candidate's resume data
        and generate up to 10 DISTINCT job titles they should target in their job search.

        CANDIDATE DATA:
        - Past Job Titles: {json.dumps(past_titles)}
        - Skills: {json.dumps(skills[:20])}
        - Education: {json.dumps(education)}
        - Summary: {summary[:500]}
        - Raw Resume Text: {raw_text[:1000]}

        RULES:
        1. Generate 7-10 titles that span the candidate's qualification range.
        2. Include EXACT-MATCH titles (what they've done before).
        3. Include ADJACENT titles (roles they could transition to based on skills).
        4. Calibrate seniority: if they have <2 years experience, use Junior/Entry-Level/Intern.
           If 2-5 years, use mid-level (no prefix). If 5+, use Senior/Lead/Staff.
        5. Every title MUST be 2-4 words. NO single-word titles like "Engineer" or "Analyst".
        6. Be SPECIFIC: "Backend Software Engineer" not just "Engineer".
        7. No duplicates. No generic titles like "Team Member" or "Professional".
        8. Order from strongest match to weakest.

        Output ONLY a JSON array of strings. Example:
        ["Senior Software Engineer", "Backend Developer", "Python Developer", "DevOps Engineer"]
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )

            titles = json.loads(response.text)

            # Validate & Clean
            cleaned = []
            for t in titles:
                if not isinstance(t, str):
                    continue
                clean = re.sub(r'[()"\'\[\]]', '', t).strip()
                # Must be multi-word
                if clean and len(clean.split()) >= 2:
                    cleaned.append(clean)

            # Deduplicate (case-insensitive)
            seen = set()
            unique = []
            for t in cleaned:
                key = t.lower()
                if key not in seen:
                    seen.add(key)
                    unique.append(t)

            result = unique[:10]
            print(f"🎯 JobTitleAgent: Generated {len(result)} titles: {result}")
            return result

        except Exception as e:
            print(f"⚠️ JobTitleAgent Error: {e}")
            # Fallback: try to extract from past job titles
            if past_titles:
                return past_titles[:3]
            return ["Software Engineer"]
