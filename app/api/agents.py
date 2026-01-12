from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body
from app.api.auth import get_current_user
from app.services.supabase_client import supabase_service
from app.agents.researcher import ResearcherAgent
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


# --- Routes ---

import httpx

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO_OWNER = os.getenv("GITHUB_REPO_OWNER")
GITHUB_REPO_NAME = os.getenv("GITHUB_REPO_NAME")
USE_GITHUB_ACTIONS = os.getenv("USE_GITHUB_ACTIONS", "true").lower() == "true"

async def dispatch_github_action(workflow_file: str, task: str, payload: dict):
    if not GITHUB_TOKEN or not GITHUB_REPO_OWNER or not GITHUB_REPO_NAME:
        logger.warning("GitHub configuration missing. Falling back to local execution (if applicable) or failing.")
        return False

    url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/actions/workflows/{workflow_file}/dispatches"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Payload must be a string for the input
    data = {
        "ref": "main", # Or current branch
        "inputs": {
            "task": task,
            "payload": json.dumps(payload)
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)
        if response.status_code != 204:
            logger.error(f"Failed to dispatch GitHub Action {workflow_file}: {response.text}")
            return False

    return True

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
    researcher_type = payload.get("researcher_type", "getwork")

    # Cap limit
    if limit > 99: limit = 99
    if limit < 1: limit = 1

    if not resume_filename:
        raise HTTPException(status_code=400, detail="resume_filename is required")

    api_key = os.getenv("GEMINI_API_KEY")
    user_id = current_user['id']

    # Update status to SEARCHING immediately for UI responsiveness
    update_research_status(user_id, resume_filename, "SEARCHING")

    # Dispatch
    if USE_GITHUB_ACTIONS:
        action_payload = {
            "user_id": user_id,
            "resume_filename": resume_filename,
            "limit": limit,
            "job_title": job_title,
            "location": location,
            "researcher_type": researcher_type
        }
        success = await dispatch_github_action("research_agent.yml", "research", action_payload)

        if success:
            return {"message": "Research started (GitHub Action)", "status": "SEARCHING"}
        else:
            # Fallback to local?
            pass

    # Local Fallback (or if Actions disabled)
    if not api_key:
        raise HTTPException(status_code=503, detail="Server misconfiguration: No API Key")

    background_tasks.add_task(
        run_research_pipeline,
        user_id=user_id,
        resume_filename=resume_filename,
        api_key=api_key,
        limit=limit,
        job_title=job_title,
        location=location,
        researcher_type=researcher_type
    )

    return {"message": "Research started (Local)", "status": "SEARCHING"}

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

    if USE_GITHUB_ACTIONS:
        action_payload = {
            "user_id": user_id,
            "job_url": job_url,
            "resume_filename": resume_filename,
            "user_profile": profile_blob
        }
        success = await dispatch_github_action("apply_agent.yml", "apply", action_payload)
        if success:
             return {"message": "Application started (GitHub Action)"}
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
        # 1. Download Resume
        try:
            remote_path = f"{user_id}/{resume_filename}"
            file_bytes = supabase_service.download_file(remote_path)

            tmp_path = f"/tmp/apply_{user_id}_{resume_filename}"
            with open(tmp_path, "wb") as f:
                f.write(file_bytes)

            # 2. Run Applier
            await run_applier_task(job_url, tmp_path, profile_blob, api_key, resume_filename=resume_filename)

            # 3. Cleanup
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        except Exception as e:
            print(f"❌ Apply Wrapper Failed: {e}")
            # Try to revert status if possible?
            supabase_service.update_lead_status_by_url(user_id, job_url, "FAILED")

    background_tasks.add_task(_download_and_apply)

    return {"message": "Application started (Local)"}
