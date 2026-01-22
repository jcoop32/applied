from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import asyncio
from app.services.agent_runner import run_research_pipeline, run_applier_task
from app.services.supabase_client import supabase_service

router = APIRouter()

class TaskPayload(BaseModel):
    type: str # "research" or "apply"
    user_id: Optional[int] = None
    resume_filename: Optional[str] = None
    api_key: Optional[str] = None
    session_id: Optional[int | str] = None
    
    # Research specific
    limit: Optional[int] = 20
    job_title: Optional[str] = None
    location: Optional[str] = None
    
    # Apply specific
    job_url: Optional[str] = None
    resume_path: Optional[str] = None # Ignored in favor of redownloading
    user_profile: Optional[Dict[str, Any]] = None
    use_cloud: bool = False
    instructions: Optional[str] = None

@router.post("/task")
async def handle_worker_task(
    payload: TaskPayload,
    x_worker_secret: str = Header(None, alias="x-worker-secret")
):
    # 1. Authenticate using Shared Secret
    expected_secret = os.getenv("WORKER_SECRET")
    if not expected_secret or x_worker_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid Worker Secret")

    print(f"👷 Cloud Worker received task: {payload.type}")

    # 2. Dispatch
    if payload.type == "research":
        if not payload.user_id or not payload.resume_filename or not payload.api_key:
             raise HTTPException(status_code=400, detail="Missing required research args")
        
        # Run asynchronously in background? Or await?
        # Since this is a worker node, we might want to await it if it's a Cloud Run Job. 
        # But if it's a Service, we should probably run background to not timeout HTTP?
        # However, Cloud Run Services have timeout. Ideally we use Cloud Run Jobs. 
        # For now, we'll await it so we can return success/failure, assuming timeout is high enough (60m).
        
        await run_research_pipeline(
            user_id=payload.user_id,
            resume_filename=payload.resume_filename,
            api_key=payload.api_key,
            limit=payload.limit,
            job_title=payload.job_title,
            location=payload.location,
            session_id=payload.session_id
        )
        return {"status": "completed", "type": "research"}

    elif payload.type == "apply":
        if not payload.job_url or not payload.resume_filename or not payload.user_profile:
             raise HTTPException(status_code=400, detail="Missing required apply args")
        
        # We need to re-download the resume here because the local path is invalid in the cloud container
        # Note: We duplicate the download logic from chat.py specifically for the worker environment
        import uuid
        user_id = payload.user_profile.get("user_id") or payload.user_profile.get("id") # Try to get ID from profile if basic user_id is missing? 
        # Actually payload.user_profile might not have user_id if it came from raw blob. 
        # But in chat.py we construct it.
        # But wait, run_applier_task takes user_profile.
        
        # Wait, payload needs user_id explicitly for download logic?
        # Let's rely on info passed.
        # Ideally we trust payload.user_profile has it, or we rely on some other way.
        # In chat.py we did: remote_path = f"{user_id}/{resume_filename}"
        
        # Let's assume we can get user_id from payload.user_id if set (task payload has it optional)
        # In chat.py call, we didn't pass user_id to payload for apply, we only put it in user_profile? 
        # Let's check agent_runner replacement... 
        # Ah, in applier payload we passed: "user_profile": user_profile. 
        # And user_profile has user_id attached usually.
        
        target_uid = payload.user_id
        if not target_uid:
             # Try extract
             target_uid = payload.user_profile.get("user_id") or payload.user_profile.get("id")
             
        if not target_uid:
             print("⚠️ Worker Warning: no user_id found for resume download. Proceeding might fail if file needed.")
        
        tmp_path = None
        try:
             # Download Resume
             remote_path = f"{target_uid}/{payload.resume_filename}"
             print(f"⬇️ Worker Downloading resume: {remote_path}")
             file_bytes = supabase_service.download_file(remote_path)
             
             tmp_id = str(uuid.uuid4())
             tmp_path = f"/tmp/worker_{tmp_id}_{payload.resume_filename}"
             with open(tmp_path, "wb") as f:
                 f.write(file_bytes)
                 
             # Run Applier
             # Note: use_cloud=True usually means use BrowserBase or similar? 
             # Or does it mean "use cloud run"?
             # In run_applier_task, use_cloud enables browser_use logic? 
             # Let's just pass what we received.
             
             await run_applier_task(
                 job_url=payload.job_url,
                 resume_path=tmp_path, # Local temp path
                 user_profile=payload.user_profile,
                 api_key=payload.api_key,
                 resume_filename=payload.resume_filename,
                 use_cloud=payload.use_cloud,
                 session_id=payload.session_id,
                 instructions=payload.instructions
             )
             return {"status": "completed", "type": "apply"}
             
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    else:
        raise HTTPException(status_code=400, detail="Unknown task type")
