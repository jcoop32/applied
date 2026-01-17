from typing import List, Dict, Any
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from app.services.supabase_client import supabase_service
from app.api.auth import get_current_user
from app.utils.resume_parser import ResumeParser
import os
import json
import tempfile

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}

# Initialize Parser
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
parser = ResumeParser(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def validate_extension(filename: str):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Uploads a resume file to Supabase storage for the current user.
    Triggers immediate parsing to populate profile data.
    """
    validate_extension(file.filename)

    try:
        content = await file.read()
        user_id = current_user['id']
        safe_name = os.path.basename(file.filename)

        # 1. Upload to Storage
        public_url = supabase_service.upload_resume(
            file_content=content,
            file_name=safe_name,
            user_id=user_id,
            content_type=file.content_type or "application/pdf"
        )

        updates = {}
        
        # 2. Trigger Parsing (if parser available)
        if parser:
            try:
                # Save temp for Gemini
                tmp_path = os.path.join(tempfile.gettempdir(), f"{user_id}_{safe_name}")
                with open(tmp_path, "wb") as f:
                    f.write(content)
                
                # Parse
                print(f"🔮 Parsing resume: {safe_name}...")
                json_str = await parser.parse_to_json(tmp_path)
                
                # Cleanup temp
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

                # Decode & Transform
                try:
                    parsed_data = json.loads(json_str)
                except json.JSONDecodeError:
                    import re
                    match = re.search(r'```json\n(.*?)\n```', json_str, re.DOTALL)
                    parsed_data = json.loads(match.group(1)) if match else {}

                if parsed_data:
                    profile_data = parser.map_to_schema(parsed_data)
                    updates["profile_data"] = profile_data
                    
                    # Also update name if found
                    if "full_name" in parsed_data and parsed_data["full_name"]:
                         updates["full_name"] = parsed_data["full_name"]
                    
                    print(f"✅ Resume parsed successfully. Profile updated.")
            
            except Exception as parse_error:
                print(f"⚠️ Parsing failed: {parse_error}")
                # We continue to at least save the file association

        # 3. Update User Profile (Primary Resume & Data)
        user_data = supabase_service.get_user_by_email(current_user['email'])
        if user_data:
            current_profile_data = user_data.get('profile_data') or {}
            
            # Merge updates if we have parsed data
            # If we don't have updates from parsing, we might still want to reset research status
            
            # Reset Research Status
            if 'research_status' in current_profile_data:
                if safe_name in current_profile_data['research_status']:
                    current_profile_data['research_status'][safe_name] = {"status": "IDLE", "updated_at": "now"}
                    # Only add to updates if not already set by parser logic (which replaces profile_data entirely?)
                    # Wait, parser replaces profile_data. We should be careful not to lose other fields if any?
                    # Schema says profile_data IS the resume data. So replacing is fine.
                    # BUT research_status is inside profile_data in the DB model?
                    # Let's check Supabase model text again:
                    # "profile_data: JSONB blob containing: ... research_status: Tracking per-resume agent states."
                    # So if we overwrite profile_data, we LOSE research_status unless we preserve it.
                    
                    if "profile_data" in updates:
                        # Restore research_status to the new object
                         updates["profile_data"]["research_status"] = current_profile_data.get('research_status', {})
                         # And reset specific one
                         updates["profile_data"]["research_status"][safe_name] = {"status": "IDLE", "updated_at": "now"}
                    else:
                        # Just updating status
                        current_profile_data['research_status'][safe_name] = {"status": "IDLE", "updated_at": "now"}
                        updates["profile_data"] = current_profile_data

            # Auto-set Primary
            if not user_data.get('primary_resume_name'):
                updates["primary_resume_name"] = safe_name
                print(f"✅ Auto-set primary resume to: {safe_name}")

            if updates:
                supabase_service.update_user_profile(user_id, updates)

        return {
            "message": "Upload successful",
            "filename": safe_name,
            "url": public_url
        }
    except Exception as e:
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/resumes")
async def list_resumes(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Lists all available resumes for the current user.
    """
    try:
        user_id = current_user['id']
        files = supabase_service.list_resumes(user_id=user_id)
        # Filter out non-allowed extensions (e.g. .json matches files)
        files = [f for f in files if any(f['name'].lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)]

        # Fetch lead counts
        counts = supabase_service.get_lead_counts(user_id)
        for f in files:
            f['job_count'] = counts.get(f['name'], 0)

        # Sort by creation date
        files.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return files
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/upload/{filename}")
async def delete_resume(
    filename: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Deletes a specific resume.
    """
    user_id = current_user['id']
    path = f"{user_id}/{filename}"

    try:
        # Check if it was the primary resume & cleanup status
        user = supabase_service.get_user_by_email(current_user['email'])
        updates = {}

        if user:
            # 1. Unset Primary
            if user.get('primary_resume_name') == filename:
                updates["primary_resume_name"] = None

            # 2. Cleanup Research Status
            profile_data = user.get('profile_data') or {}
            if 'research_status' in profile_data and filename in profile_data['research_status']:
                del profile_data['research_status'][filename]
                updates["profile_data"] = profile_data

            if updates:
                 supabase_service.update_user_profile(user_id, updates)

        # Invalidate leads cache for the deleted resume
        supabase_service.invalidate_leads_cache(user_id, filename)

        supabase_service.delete_file(path)
        return {"message": "Deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
