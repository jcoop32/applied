from fastapi import APIRouter, Depends, HTTPException, Body
from app.api.auth import get_current_user
from app.services.supabase_client import supabase_service
from app.utils.resume_parser import ResumeParser
import os
import json
import tempfile



router = APIRouter()

# Initialize Parser with Gemini Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
parser = ResumeParser(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

@router.get("")
async def get_profile(current_user: dict = Depends(get_current_user)):
    """
    Get current user profile (including primary_resume_name and profile_data).
    """
    # Force refresh user data from DB to get latest columns
    user = supabase_service.get_user_by_email(current_user['email'])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Remove password hash for security
    user.pop('password_hash', None)
    return user

@router.patch("")
async def update_profile(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Update user profile fields.
    Allowed fields: full_name, primary_resume_name, profile_data
    """
    user_id = current_user['id']
    allowed_keys = {'full_name', 'primary_resume_name', 'profile_data'}

    # Filter data
    clean_data = {k: v for k, v in data.items() if k in allowed_keys}

    if not clean_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    updated_user = supabase_service.update_user_profile(user_id, clean_data)
    if not updated_user:
        raise HTTPException(status_code=500, detail="Failed to update profile")

    updated_user.pop('password_hash', None)
    return updated_user

@router.post("/parse")
async def parse_resume(
    resume_path: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """
    Triggers Gemini to parse the resume file and return the structured JSON.
    Also auto-saves it to the user's profile_data.
    """
    if not parser:
         raise HTTPException(status_code=503, detail="Resume Parser service unavailable (Missing API Key)")

    user_id = current_user['id']

    # Handle filename vs full path
    # If client sends just "resume.pdf", we convert to "{user_id}/resume.pdf"
    if "/" not in resume_path:
        resume_path = f"{user_id}/{resume_path}"

    try:
        # Check if file exists/ownership via list?
        # Or just try to download and catch error.
        # Supabase download checks path.

        # 1. Download file content
        file_bytes = supabase_service.download_file(resume_path)

        # 2. Save temporarily for the parser
        # Use user_id prefix to avoid collision in /tmp
        safe_name = os.path.basename(resume_path)
        tmp_path = f"/tmp/{user_id}_{safe_name}"

        with open(tmp_path, "wb") as f:
            f.write(file_bytes)

        # 3. Parse
        json_str = await parser.parse_to_json(tmp_path)

        # 4. Clean up
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        # 5. Parse JSON string to Object
        try:
             parsed_data = json.loads(json_str)
        except json.JSONDecodeError:
             # Fallback if LLM returned markdown block
             import re
             match = re.search(r'```json\n(.*?)\n```', json_str, re.DOTALL)
             if match:
                 parsed_data = json.loads(match.group(1))
             else:
                 parsed_data = {"raw_text": json_str}

        # --- Data Transformation (Flat -> Profile Schema) ---
        transformed_data = {
            "contact_info": {
                "phone": parsed_data.get("phone", ""),
                "linkedin": parsed_data.get("linkedin", ""),
                "portfolio": parsed_data.get("website", ""),
                "address": parsed_data.get("location", "")
            },
            "summary": parsed_data.get("summary", ""),
            "skills": parsed_data.get("skills", []),
            "experience": [],
            "education": []
        }

        # Map Experience
        # LLM output keys: company, title, start_date, end_date, description
        # UI expects: company, title, duration, responsibilities
        raw_exp = parsed_data.get("work_experience", [])
        for item in raw_exp:
            duration = f"{item.get('start_date', '')} - {item.get('end_date', '')}"
            transformed_data["experience"].append({
                "company": item.get("company", ""),
                "title": item.get("title", ""),
                "duration": duration.strip(" - "),
                "responsibilities": item.get("description", "")
            })

        # Map Education
        # LLM output keys: school, degree, graduation_year
        # UI expects: school, degree, date
        raw_edu = parsed_data.get("education", [])
        for item in raw_edu:
            transformed_data["education"].append({
                "school": item.get("school", ""),
                "degree": item.get("degree", ""),
                "date": item.get("graduation_year", "")
            })

        # 6. Auto-Save to Profile
        # We also want to update the root full_name if found
        update_payload = {"profile_data": transformed_data}
        if "full_name" in parsed_data and parsed_data["full_name"]:
            update_payload["full_name"] = parsed_data["full_name"]

        supabase_service.update_user_profile(user_id, update_payload)

        return update_payload

    except Exception as e:
        print(f"Parse Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/summary")
async def generate_resume_summary(
    resume_path: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """
    Generates a professional summary from the specified resume.
    """
    if not resume_path:
        raise HTTPException(status_code=400, detail="Resume path required")

    user_id = current_user['id']
    if "/" not in resume_path:
        resume_path = f"{user_id}/{resume_path}"

    try:
        # Download from Supabase
        file_bytes = supabase_service.download_file(resume_path)

        # Save to temp
        safe_name = os.path.basename(resume_path)
        tmp_path = os.path.join(tempfile.gettempdir(), f"{user_id}_{safe_name}")

        with open(tmp_path, "wb") as f:
            f.write(file_bytes)

        parser = ResumeParser(os.getenv("GEMINI_API_KEY"))
        summary = await parser.generate_summary(tmp_path)

        # Clean up
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        return {"summary": summary.strip()}

    except Exception as e:
        print(f"Summary Generation Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
