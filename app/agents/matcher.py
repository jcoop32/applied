import json
import asyncio
from google import genai
from pydantic import BaseModel, Field
from typing import List, Dict, Any

class MatchAnalysis(BaseModel):
    is_match: bool = Field(description="False if strict seniority mismatch or completely wrong field")
    score: int = Field(description="Suitability score 0-100")
    reason: str = Field(description="Brief string why it matched or failed")

class MatcherAgent:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.5-flash"

    async def filter_and_score_leads(self, leads: List[Dict], profile: dict, limit: int = 10) -> List[Dict]:
        """
        Takes potentially hundreds of raw leads, scores them, and returns the top matches.
        """
        print(f"🧠 Matcher: Scoring {len(leads)} raw leads against profile...")

        matches = []

        # Process in batches to avoid rate limits if needed, but for now we loop
        # We can run these in parallel chunks if speed is needed later
        sema = asyncio.Semaphore(5) # Concurrency limit

        async def _score(lead):
            async with sema:
                return await self._analyze_lead(lead, profile)

        tasks = [_score(lead) for lead in leads]
        results = await asyncio.gather(*tasks)

        for lead, analysis in zip(leads, results):
            if analysis['is_match']:
                lead['match_score'] = analysis['score']
                lead['match_reason'] = analysis['reason']
                matches.append(lead)
            else:
                # Optional: Keep rejected ones for audit? User implies we just want the good ones in the final list
                pass

        # Sort by Score Descending
        matches.sort(key=lambda x: x.get('match_score', 0), reverse=True)

        # Return top N
        print(f"   Found {len(matches)} valid matches. Returning top {limit}.")
        return matches[:limit]

    async def _analyze_lead(self, lead: dict, profile: dict) -> Dict:
        """
        LLM "Judge" to score a single lead.
        """
        try:
            prompt = f"""
            Act as a strict Recruiter. Compare Candidate vs Job.

            CANDIDATE:
            Summary: {profile.get('summary', '')[:500]}
            Skills: {', '.join(profile.get('skills', [])[:10])}
            Level: {profile.get('experience_level', 'Unknown')}

            JOB:
            Title: {lead.get('title')}
            Company: {lead.get('company')}
            Query Used: {lead.get('query_source')}
            Snippet: {lead.get('snippet')}

            TASK:
            1. **Strict Seniority Check**: Reject Senior/Lead/Manager if Candidate is Junior.
            2. **Domain Check**: Reject if job is purely Marketing/Sales/HR (unless candidate is that).
            3. **Score (0-100)**:
               - 100: Perfect title + skill match.
               - 80: Good title, some skills.
               - 0-50: Wrong title or weak match.
            4. **Match Boolean**: logic: if Score > 60 and Seniority OK -> True.

            Return JSON: {{ "is_match": bool, "score": int, "reason": "str" }}
            """

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            return json.loads(response.text)
        except Exception as e:
            # Default fail
            return {"is_match": False, "score": 0, "reason": f"Error: {e}"}
