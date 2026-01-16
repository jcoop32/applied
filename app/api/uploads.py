from typing import List, Dict, Any
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from app.services.supabase_client import supabase_service
from app.api.auth import get_current_user

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}

def validate_extension(filename: str):
    import os
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
    """
    validate_extension(file.filename)

    try:
        content = await file.read()

        # Use user_id from token
        user_id = current_user['id']

        public_url = supabase_service.upload_resume(
            file_content=content,
            file_name=file.filename,
            user_id=user_id,
            content_type=file.content_type or "application/pdf"
        )

        # Logic: If user has no primary resume, set this one!
        # Re-fetch user to check (in case token is stale regarding DB state)
        # Note: Optimization would be to check the 'current_user' dict if we included it there,
        # but for now a fetch is safer.
        # Logic: Update Primary Resume & Reset Status
        # We must fetch the current profile to safely update `profile_data`
        user_data = supabase_service.get_user_by_email(current_user['email'])
        if not user_data:
             # Should not happen given auth
             pass
        else:
            updates = {}
            current_profile_data = user_data.get('profile_data') or {}

            # 1. Reset Research Status (Fix for Stale State bug)
            if 'research_status' in current_profile_data:
                if file.filename in current_profile_data['research_status']:
                    # Reset to IDLE or remove
                    current_profile_data['research_status'][file.filename] = {"status": "IDLE", "updated_at": "now"}
                    updates["profile_data"] = current_profile_data

            # 2. Auto-set Primary if empty
            if not user_data.get('primary_resume_name'):
                updates["primary_resume_name"] = file.filename
                print(f"✅ Auto-set primary resume to: {file.filename}")

            if updates:
                try:
                    supabase_service.update_user_profile(user_id, updates)
                except Exception as e:
                    print(f"⚠️ Failed to update profile metadata: {e}")

        return {
            "message": "Upload successful",
            "filename": file.filename,
            "url": public_url
        }
    except Exception as e:
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
