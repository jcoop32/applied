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
        # 4. Multimodal Call
        from fastapi.concurrency import run_in_threadpool
        
        response = await run_in_threadpool(
            self.client.models.generate_content,
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

    def map_to_schema(self, parsed_data):
        """
        Maps the flat JSON from Gemini to the nested profile schema used by the frontend/DB.
        """
        from datetime import datetime
        
        def parse_date_string(date_str):
            if not date_str: return {"month": "", "year": ""}
            date_str = str(date_str).strip()
            if date_str.lower() in ['present', 'current', 'now']:
                return {"month": "", "year": "", "is_current": True}
            
            try:
                dt = datetime.strptime(date_str, "%b %Y")
                return {"month": dt.strftime("%B"), "year": str(dt.year)}
            except ValueError: pass
            
            try:
                dt = datetime.strptime(date_str, "%B %Y")
                return {"month": dt.strftime("%B"), "year": str(dt.year)}
            except ValueError: pass
            
            if date_str.isdigit() and len(date_str) == 4:
                return {"month": "", "year": date_str}
            
            return {"month": "", "year": ""}

        transformed = {
            "phone": parsed_data.get("phone", ""),
            "linkedin": parsed_data.get("linkedin", ""),
            "portfolio": parsed_data.get("website", ""),
            "address": parsed_data.get("location", ""),
            "summary": parsed_data.get("summary", ""),
            "skills": parsed_data.get("skills", []),
            "experience": [],
            "education": []
        }

        # Map Experience
        for item in parsed_data.get("work_experience", []):
            start_str = item.get('start_date', '')
            end_str = item.get('end_date', '')
            start_p = parse_date_string(start_str)
            end_p = parse_date_string(end_str)
            
            transformed["experience"].append({
                "company": item.get("company", ""),
                "title": item.get("title", ""),
                "duration": f"{start_str} - {end_str}".strip(" - "),
                "responsibilities": item.get("description", ""),
                "start_month": start_p.get("month", ""),
                "start_year": start_p.get("year", ""),
                "end_month": end_p.get("month", ""),
                "end_year": end_p.get("year", ""),
                "is_current": end_p.get("is_current", False)
            })

        # Map Education
        for item in parsed_data.get("education", []):
            grad_year = item.get('graduation_year', '')
            end_p = parse_date_string(grad_year)
            
            transformed["education"].append({
                "school": item.get("school", ""),
                "degree": item.get("degree", ""),
                "date": grad_year,
                "end_year": end_p.get("year", grad_year),
                "end_month": end_p.get("month", "")
            })
            
        return transformed


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
