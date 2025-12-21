import os
from pypdf import PdfReader
from google import genai

class ResumeParser:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)

    def extract_text(self, pdf_path):
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            content = page.extract_text()
            if content:
                text += content
        return text

    async def parse_to_json(self, pdf_path):
        raw_text = self.extract_text(pdf_path)

        # We define a manual schema that avoids 'additional_properties'
        manual_schema = {
            "type": "OBJECT",
            "properties": {
                "full_name": {"type": "STRING"},
                "email": {"type": "STRING"},
                "phone": {"type": "STRING"},
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
                            "end_date": {"type": "STRING"},
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

        prompt = f"Extract all resume info into JSON:\n{raw_text}"

        response = self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': manual_schema,
            }
        )

        return response.text
