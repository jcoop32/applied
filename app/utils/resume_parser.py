import os
from google import genai
from google.genai import types

class ResumeParser:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)

    async def parse_to_json(self, pdf_path):
        # 1. Read the PDF as binary (Visual Processing)
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # 2. Define the Schema (Same as before, but critical for consistency)
        manual_schema = {
            "type": "OBJECT",
            "properties": {
                "full_name": {"type": "STRING"},
                "email": {"type": "STRING"},
                "phone": {"type": "STRING"},
                "linkedin": {"type": "STRING", "description": "LinkedIn profile URL"},
                "website": {"type": "STRING", "description": "Personal website or portfolio URL"},
                "location": {"type": "STRING"},
                "skills": {"type": "ARRAY", "items": {"type": "STRING"}},
                "summary": {"type": "STRING"},
                "work_experience": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "company": {"type": "STRING"},
                            "title": {"type": "STRING"},
                            "start_date": {"type": "STRING"},
                            "end_date": {"type": "STRING", "description": "Use 'Present' if currently employed"},
                            "description": {"type": "STRING"}
                        }
                    }
                },
                "education": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "school": {"type": "STRING"},
                            "degree": {"type": "STRING"},
                            "graduation_year": {"type": "STRING"}
                        }
                    }
                }
            }
        }

        # 3. Optimized Prompt
        # We ask it to use visual layout cues (columns, bold text) to parse correctly.
        prompt = """
        Analyze this resume document visually. Extract all information into the specified JSON format.

        Guidelines:
        - If the resume has multiple columns, read them logically.
        - Infer skills from the 'Technical Skills' section or project descriptions.
        - Standardize phone numbers to (XXX) XXX-XXXX format if possible.
        - For 'end_date', use the word "Present" if the candidate is still working there.
        """

        # 4. Multimodal Call
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                prompt
            ],
            config={
                'response_mime_type': 'application/json',
                'response_schema': manual_schema,
            }
        )
        return response.text


    async def generate_summary(self, pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        prompt = """
        Analyze this resume and write a concise, professional summary (max 3 sentences) suitable for a LinkedIn profile or resume header.
        Focus on key skills, years of experience, and primary achievements.
        Do not use specific names like "I am a..." just start with the role/adjective like "Experienced Software Engineer...".
        """

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                prompt
            ]
        )
        return response.text
