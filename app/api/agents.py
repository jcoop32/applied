from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body
from app.api.auth import get_current_user
from app.services.supabase_client import supabase_service

from app.agents.matcher import MatcherAgent
from app.agents.applier import ApplierAgent
from app.services.agent_runner import run_research_pipeline, update_research_status
import os
import json
import logging
from typing import Dict, Any

router = APIRouter()
logger = logging.getLogger(__name__)

from app.services.agent_runner import run_research_pipeline, update_research_status, run_applier_task
from app.services.github import dispatch_github_action
from app.services.task_manager import task_manager
import asyncio

# --- Routes ---

USE_GITHUB_ACTIONS = os.getenv("USE_GITHUB_ACTIONS", "true").lower() == "true"

@router.post("/research")
async def trigger_research(
    background_tasks: BackgroundTasks,
    payload: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Payload: { "resume_filename": "..." }
    """
    resume_filename = payload.get("resume_filename")
    limit = payload.get("limit", 20)
    job_title = payload.get("job_title") # Optional Manual Override
    location = payload.get("location")   # Optional Manual Override


    # Cap limit
    if limit > 99: limit = 99
    if limit < 1: limit = 1

    if not resume_filename:
        raise HTTPException(status_code=400, detail="resume_filename is required")

    api_key = os.getenv("GEMINI_API_KEY")
    user_id = current_user['id']

    # Update status to SEARCHING immediately for UI responsiveness
    update_research_status(user_id, resume_filename, "SEARCHING")

    # Create Persistent Chat Session (Always, for visibility)
    # Note: If GHA runs, it might not log to this session unless configured, 
    # but at least the user sees "Research: ..." in their list.
    session_title = f"Research: {resume_filename}"
    chat_session = supabase_service.create_chat_session(user_id, session_title)
    session_id = chat_session['id'] if chat_session else None

    # Immediate feedback in Chat
    if session_id:
        supabase_service.save_chat_message(session_id, "model", f"🕵️ Research session initialized for **{resume_filename}**. Starting agent...")

    # Dispatch
    if USE_GITHUB_ACTIONS:
        action_payload = {
            "user_id": user_id,
            "resume_filename": resume_filename,
            "limit": limit,
            "job_title": job_title,
            "location": location,
            "session_id": session_id # Pass session ID to GHA
        }
        success = await dispatch_github_action("research_agent.yml", "research", action_payload)

        if success:
            return {"message": "Research started (GitHub Action)", "status": "SEARCHING", "session_id": session_id}
        else:
            # Fallback to local?
            pass

    # Local Fallback (or if Actions disabled)
    if not api_key:
        raise HTTPException(status_code=503, detail="Server misconfiguration: No API Key")

    # Use asyncio task instead of BackgroundTasks to allow cancellation
    task = asyncio.create_task(
        run_research_pipeline(
            user_id=user_id,
            resume_filename=resume_filename,
            api_key=api_key,
            limit=limit,
            job_title=job_title,
            location=location,
            session_id=session_id
        )
    )
    if session_id:
        task_manager.register_task(str(session_id), task)

    return {"message": "Research started (Local)", "status": "SEARCHING", "session_id": session_id}

@router.get("/matches")
async def get_matches(
    resume_filename: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Returns existing matches from DB and current status.
    """
    user_id = current_user['id']

    # 1. Get Status
    # Use optimized fetch for just the research status (profile_data)
    # We use user_id from the token (cached) so we don't need to look up by email again
    profile_data = supabase_service.get_research_status(user_id)
    status_map = profile_data.get('research_status', {})  # profile_data might be dict or None
    if not status_map: status_map = {}
    current_status = status_map.get(resume_filename, {"status": "IDLE"})

    # 2. Get Matches from DB
    matches = []
    # Always fetch if there's data, regardless of status
    matches = supabase_service.get_leads(user_id, resume_filename)

    # Fallback to JSON if DB empty? (Optional, maybe not needed if migration is clean slate)
    if not matches and current_status.get("status") == "COMPLETED":
        # Try legacy JSON
         try:
            target_file = f"{user_id}/matches_{resume_filename}.json"
            content_bytes = supabase_service.download_file(target_file)
            matches = json.loads(content_bytes)
         except:
            pass

    return {
        "status": current_status,
        "matches": matches
    }

@router.post("/apply")
async def trigger_apply(
    background_tasks: BackgroundTasks,
    payload: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Payload: { "job_url": "...", "resume_filename": "..." }
    """
    job_url = payload.get("job_url")
    resume_filename = payload.get("resume_filename")
    instructions = payload.get("instructions") # Optional
    mode = payload.get("mode", "local") # Extract mode (local, cloud_run, browser_use_cloud)

    if not job_url or not resume_filename:
        raise HTTPException(status_code=400, detail="job_url and resume_filename required")

    api_key = os.getenv("GEMINI_API_KEY")

    # Get Profile Data for the applier
    user_data = supabase_service.get_user_by_email(current_user['email'])
    profile_blob = user_data.get('profile_data', {})

    # Add email/phone from top level if missing in blob
    if 'email' not in profile_blob:
        profile_blob['email'] = current_user['email']
    if 'full_name' not in profile_blob and user_data.get('full_name'):
        profile_blob['full_name'] = user_data.get('full_name')

    user_id = current_user['id']
    
    # IMMEDIATE STATUS UPDATE: Mark as IN_PROGRESS so UI reflects it immediately
    supabase_service.update_lead_status_by_url(user_id, job_url, "IN_PROGRESS", resume_filename=resume_filename)

    # Logic Switch
    should_dispatch_github = False
    
    # Legacy 'github' mode support if we re-introduce it
    if mode == 'github':
        should_dispatch_github = True
    elif USE_GITHUB_ACTIONS and mode == 'gha': # Explicit GHA request
        should_dispatch_github = True
    
    # Otherwise we rely on agent_runner to handle local/cloud_run/browser_use_cloud logic

    # Create Persistent Chat Session (Always)
    session_title = f"Apply: {job_url}"
    chat_session = supabase_service.create_chat_session(user_id, session_title)
    session_id = chat_session['id'] if chat_session else None

    if session_id:
        supabase_service.save_chat_message(session_id, "model", f"🚀 Application session initialized for **{job_url}**. Starting agent...")


    if should_dispatch_github:
        action_payload = {
            "user_id": user_id,
            "job_url": job_url,
            "resume_filename": resume_filename,
            "user_profile": profile_blob,
            "session_id": session_id, # Pass session ID
            "instructions": instructions
        }
        success = await dispatch_github_action("apply_agent.yml", "apply", action_payload)
        if success:
             return {"message": "Application started (GitHub Action)", "session_id": session_id}
        else:
             logger.error("❌ Failed to dispatch GitHub Action for Apply. Falling back to local/background task if key available.")

    # Construct resume path (temp download needed? Applier handles local path logic)
    # The ApplierAgent.apply methods expects a LOCAL file path.
    # We need to download it first or let Applier handle it.
    
    if not api_key:
        # If we failed GH action AND no API key, we can't do anything.
        raise HTTPException(status_code=500, detail="Failed to start application agent (No GH Token & No API Key)")

    # If local fallback:
    async def _download_and_apply():
        # session_id passed from outer scope
        
        # 1. Download Resume
        try:
            remote_path = f"{user_id}/{resume_filename}"
            file_bytes = supabase_service.download_file(remote_path)

            tmp_path = f"/tmp/apply_{user_id}_{resume_filename}"
            with open(tmp_path, "wb") as f:
                f.write(file_bytes)

            # 2. Run Applier
            await run_applier_task(job_url, tmp_path, profile_blob, api_key, resume_filename=resume_filename, execution_mode=mode, session_id=session_id, instructions=instructions)

            # 3. Cleanup
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        except asyncio.CancelledError:
             # Handle outer cancellation if wrapper is cancelled
             print(f"🛑 Wrapper: Applier Cancelled for {job_url}")
             supabase_service.save_chat_message(session_id, "model", "🛑 Application Cancelled by user.")

        except Exception as e:
            print(f"❌ Apply Wrapper Failed: {e}")
            # Try to revert status if possible?
            supabase_service.update_lead_status_by_url(user_id, job_url, "FAILED")
            if session_id:
                supabase_service.save_chat_message(session_id, "model", f"❌ Application Failed: {e}")

    # Launch task
    task = asyncio.create_task(_download_and_apply())
    if session_id:
         task_manager.register_task(str(session_id), task)

    return {"message": "Application started (Local)"}

@router.post("/cancel/{session_id}")
async def cancel_agent_task(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Cancels a running agent task associated with the session_id.
    """
    success = await task_manager.cancel_task(session_id)
    if success:
        return {"message": "Task cancellation requested."}
    else:
        # It might be finished or never existed locally (e.g. GHA)
        # We return 200 anyway to not break UI
        return {"message": "Task not found or already finished."}
