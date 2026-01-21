from fastapi import APIRouter, Depends, HTTPException, Body
from app.api.auth import get_current_user
from app.services.supabase_client import supabase_service
from app.utils.resume_parser import ResumeParser
import os
import json
import tempfile
from datetime import datetime




router = APIRouter()

def parse_date_string(date_str):
    """
    Parses "Jan 2020", "January 2020", "2020", or "Present"
    Returns {month, year, is_current}
    """
    if not date_str:
        return {"month": "", "year": ""}
    
    date_str = str(date_str).strip()
    if date_str.lower() in ['present', 'current', 'now']:
        return {"month": "", "year": "", "is_current": True}

    # Try Month Year (e.g. "Jan 2020", "January 2020")
    try:
        dt = datetime.strptime(date_str, "%b %Y")
        return {"month": dt.strftime("%B"), "year": str(dt.year)}
    except ValueError:
        pass

    try:
        dt = datetime.strptime(date_str, "%B %Y")
        return {"month": dt.strftime("%B"), "year": str(dt.year)}
    except ValueError:
        pass

    # Try just Year (e.g. "2020")
    if date_str.isdigit() and len(date_str) == 4:
        return {"month": "", "year": date_str}

    # Fallback/Empty
    return {"month": "", "year": ""}

# Initialize Parser with Gemini Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
parser = ResumeParser(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

@router.get("")
async def get_profile(current_user: dict = Depends(get_current_user)):
    """
    Get current user profile (merging Auth data and Profile data).
    """
    # 1. Fetch Profile Data
    profile = supabase_service.get_user_profile(current_user['id'])
    
    # 2. Merge with Current User (Email, ID)
    if profile:
        # Merge, ensuring we don't overwrite critical auth fields if namespace collides (which it shouldn't)
        merged_user = {**current_user, **profile}
    else:
        # Should ideally not happen if Trigger works, but fallback to just auth info
        merged_user = current_user

    # Remove sensitive data
    merged_user.pop('password_hash', None)
    
    return merged_user

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

    # Update Profiles Table
    updated_profile = supabase_service.update_user_profile(user_id, clean_data)
    if not updated_profile:
        raise HTTPException(status_code=500, detail="Failed to update profile")

    # Merge for return
    merged_user = {**current_user, **updated_profile}
    merged_user.pop('password_hash', None)
    return merged_user

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
        transformed_data = parser.map_to_schema(parsed_data)

        # 6. Auto-Save to Profile
        # We also want to update the root full_name if found
        update_payload = {"profile_data": transformed_data}
        if "full_name" in parsed_data and parsed_data["full_name"]:
            update_payload["full_name"] = parsed_data["full_name"]

        supabase_service.update_user_profile(user_id, update_payload)

        return update_payload

    except Exception as e:
        print(f"Parse Error: {e}")
        # Log to file for debugging
        with open("error_log.txt", "a") as log_file:
            import traceback
            log_file.write(f"\n[{datetime.now()}] Parse Error: {str(e)}\n")
            log_file.write(traceback.format_exc())
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
