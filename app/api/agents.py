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

# --- Helper: Status Persistence ---
def update_research_status(user_id: int, resume_filename: str, status: str):
    """
    Updates the 'research_status' in the user's profile_data.
    States: IDLE, SEARCHING, COMPLETED, FAILED
    """
    try:
        # 1. Fetch current profile
        # We need to fetch the raw data to avoid overwriting other potential updates
        # But supabase_service.get_user_by_email might be too heavy if we just have ID.
        # Actually `update_user_profile` updates columns. `profile_data` is a single column.
        # So we must Read -> Modify -> Write.

        # We don't have get_user_by_id in service, relying on what we have or adding it.
        # Service has `update_user_profile(user_id, ...)`
        # Let's try to fetch user by ID indirectly or assume we can pass a partial update to the JSONB if Postgres?
        # Supabase Python client `update` usually replaces the whole JSONB object if passed as a dict.
        # To update a deep key, we usually need a Postgres function or client-side merge.
        # I will do client-side merge for safety.

        # NOTE: accessing supabase client directly for get_by_id if needed, or allow passing current_user from router if possible context.
        # But this runs in background, so `current_user` is not available.
        # I will start by fetching the user using the service (adding a method if needed, or using a raw call).
        # Service `get_user_by_email` is available? No, we have user_id.
        # I'll add `get_user_by_id` to service or use `select * from users where id=...`

        response = supabase_service.client.table("users").select("profile_data").eq("id", user_id).execute()
        if not response.data:
            return

        current_data = response.data[0].get("profile_data") or {}

        # Ensure structure
        if "research_status" not in current_data:
            current_data["research_status"] = {}

        current_data["research_status"][resume_filename] = {
            "status": status,
            "updated_at": str(os.times()) # timestamps, just string or datetime
        }

        supabase_service.update_user_profile(user_id, {"profile_data": current_data})

    except Exception as e:
        logger.error(f"Failed to update research status: {e}")

# --- Background Task Wrappers ---

async def run_research_pipeline(user_id: int, resume_filename: str, api_key: str):
    print(f"🕵️ Background: Starting Research for {resume_filename} ...")
    update_research_status(user_id, resume_filename, "SEARCHING")

    try:
        # 1. Fetch Resume & Parse (or get cached profile)
        # We need the candidate profile to generate strategy.
        # Check if profile_data has parsed info?
        # For simplicity, we rescan or expect it in profile_data.
        # But user might have multiple resumes.
        # Let's Download -> Parse to be sure we have the specific resume's data.

        # ... Or check `profile_data` for this resume?
        # The current `api/profile.py` saves parsed data to the ROOT `profile_data`.
        # This implies only ONE active resume profile at a time.
        # I'll stick to that assumption for now, or Parsing -> JSON.

        # Let's try to download and parse fresh to be robust.

        # Setup Agents
        researcher = ResearcherAgent(api_key=api_key)

        # Retrieve Profile Data (Candidate Info)
        # We can fetch the user to get `profile_data` which allegedly contains the parsed resume.
        user_response = supabase_service.client.table("users").select("profile_data").eq("id", user_id).execute()
        profile_blob = user_response.data[0].get("profile_data", {}) if user_response.data else {}

        # If the blob looks like a parsed resume, use it.
        # Otherwise, we might need to Trigger Parse.
        # For now, assume it's there or pass reasonable defaults.

        # 2. Research
        leads = await researcher.gather_leads(profile_blob, limit=20)

        # 3. Match
        matcher = MatcherAgent(api_key=api_key)
        scored_matches = await matcher.filter_and_score_leads(leads, profile_blob, limit=10)

        # 4. Save Results
        # Save to Storage as JSON
        results_filename = f"matches_{resume_filename}.json" # e.g. matches_resume.pdf.json

        # Serialize
        json_bytes = json.dumps(scored_matches, indent=2).encode('utf-8')

        supabase_service.upload_file(
            file_content=json_bytes,
            file_name=results_filename,
            user_id=user_id,
            content_type="application/json"
        )

        # Save to DB (Table)
        try:
             supabase_service.save_leads_bulk(user_id, resume_filename, scored_matches)
        except Exception as db_err:
             print(f"⚠️ DB Save Failed: {db_err}")

        print(f"✅ Background: Research Completed. Saved {len(scored_matches)} matches.")
        update_research_status(user_id, resume_filename, "COMPLETED")

    except Exception as e:
        print(f"❌ Background: Research Failed: {e}")
        update_research_status(user_id, resume_filename, "FAILED")


async def run_applier_task(job_url: str, resume_path: str, user_profile: dict, api_key: str):
    print(f"🚀 Background: Applying to {job_url} ...")
    try:
        applier = ApplierAgent(api_key=api_key)
        # Headless True by default as requested
        # Note: ApplierAgent code currently might default to False, checking/patching later.
        # But we can't easily patch the init without changing the class.
        # The prompt mentioned "headless true". I will update ApplierAgent class separately.

        result_status = await applier.apply(job_url, user_profile, resume_path)
        print(f"🏁 Background: Applier finished: {result_status}")

        # Optional: Save application log to DB?

    except Exception as e:
        print(f"❌ Background: Applier Failed: {e}")


# --- Routes ---

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
    if not resume_filename:
        raise HTTPException(status_code=400, detail="resume_filename is required")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Server misconfiguration: No API Key")

    # Trigger background task
    background_tasks.add_task(
        run_research_pipeline,
        user_id=current_user['id'],
        resume_filename=resume_filename,
        api_key=api_key
    )

    return {"message": "Research started", "status": "SEARCHING"}

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
    # We fetch fresh user data
    user_data = supabase_service.get_user_by_email(current_user['email']) # This re-fetches
    status_map = user_data.get('profile_data', {}).get('research_status', {})
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

    # Construct resume path (temp download needed? Applier handles local path logic)
    # The ApplierAgent.apply methods expects a LOCAL file path.
    # We need to download it first or let Applier handle it.
    # The current ApplierAgent code:
    #   if not os.path.exists(resume_path): return Error
    # So we MUST download it to a temp path here in the background task.

    # We'll wrap the download in the background task or do it here?
    # Doing it in background is safer for latency.

    async def _download_and_apply():
        # 1. Download Resume
        try:
            remote_path = f"{user_id}/{resume_filename}"
            file_bytes = supabase_service.download_file(remote_path)

            tmp_path = f"/tmp/apply_{user_id}_{resume_filename}"
            with open(tmp_path, "wb") as f:
                f.write(file_bytes)

            # 2. Run Applier
            await run_applier_task(job_url, tmp_path, profile_blob, api_key)

            # 3. Cleanup
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        except Exception as e:
            print(f"❌ Apply Wrapper Failed: {e}")

    user_id = current_user['id']
    background_tasks.add_task(_download_and_apply)

    return {"message": "Application started"}
