import json
from google import genai
from pydantic import BaseModel, Field

class MatchResult(BaseModel):
    match_score: int = Field(description="Score from 0-100")
    explanation: str = Field(description="Brief reasoning for the score")
    missing_skills: list[str] = Field(description="Skills required by job but missing in resume")
    tailoring_tip: str = Field(description="One tip to improve the resume for this specific job")

class MatcherAgent:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.5-flash"

    async def score_job(self, resume_data, job_content):
        """
        Analyzes the fit between the resume and a job description.
        """
        prompt = f"""
        Act as a professional recruiter. Compare the following Candidate Profile
        against the Job Description provided.

        CANDIDATE PROFILE:
        {json.dumps(resume_data, indent=2)}

        JOB DESCRIPTION:
        {job_content}

        Provide a structured match analysis. Be honest and critical.
        """

        response = self.client.models.generate_content(
            model=self.model_id,
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': MatchResult
            }
        )

        return json.loads(response.text)
