
import os
import json
import logging
import asyncio
from app.services.supabase_client import supabase_service
from app.services.log_stream import log_stream_manager
import traceback

from app.agents.google_researcher import GoogleResearcherAgent
from app.agents.matcher import MatcherAgent
from app.agents.applier import ApplierAgent

logger = logging.getLogger(__name__)

def update_research_status(user_id: int, resume_filename: str, status: str, last_log: str = None):
    """
    Updates the 'research_status' in the user's profile_data.
    States: IDLE, QUEUED, SEARCHING, COMPLETED, FAILED
    """
    try:
        response = supabase_service.client.table("profiles").select("profile_data").eq("user_id", user_id).execute()
        if not response.data:
            return

        current_data = response.data[0].get("profile_data") or {}
        if "research_status" not in current_data:
            current_data["research_status"] = {}

        current_data["research_status"][resume_filename] = {
            "status": status,
            "updated_at": str(os.times())
        }
        
        if last_log:
             current_data["research_status"][resume_filename]["last_log"] = last_log

        supabase_service.update_user_profile(user_id, {"profile_data": current_data})

    except Exception as e:
        logger.error(f"Failed to update research status: {e}")



async def check_cancellation(user_id: int, resume_filename: str):
    """Checks if the research task has been cancelled by the user."""
    try:
        response = supabase_service.client.table("profiles").select("profile_data").eq("user_id", user_id).execute()
        if response.data:
            data = response.data[0].get("profile_data", {})
            status_entry = data.get("research_status", {}).get(resume_filename, {})
            if status_entry.get("status") == "CANCEL_REQUESTED":
                return True
    except Exception:
        pass
    return False

async def run_research_pipeline(user_id: int, resume_filename: str, api_key: str, limit: int = 20, job_title: str = None, location: str = None, session_id: int = None):
    print(f"🕵️ Worker: Starting Research for {resume_filename} with limit {limit} (Type: Google)...")
    
    # Broadcast Function helper
    async def log(msg, type="log"):
        if session_id:
            await log_stream_manager.broadcast(str(session_id), msg, type=type)
        
        # Sync simple log to profile for non-session listeners (Dashboard UI)
        # We only do this for major info logs to avoid DB Thrashing
        if type in ["log", "complete", "error", "warning"]:
             # Run in background to not block
             asyncio.create_task(asyncio.to_thread(update_research_status, user_id, resume_filename, "SEARCHING", last_log=msg))

    await log(f"Starting research pipeline for {resume_filename}...")
    
    # Cloud Dispatch Check
    cloud_url = os.getenv("CLOUD_RUN_URL")
    if cloud_url and not os.getenv("IS_CLOUD_WORKER"):
        import httpx
        print(f"🚀 Dispatching Research task to Cloud Worker: {cloud_url}")
        await log("Dispatching to Cloud Worker...")
        
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "type": "research",
                    "user_id": user_id,
                    "resume_filename": resume_filename,
                    "api_key": api_key,
                    "limit": limit,
                    "job_title": job_title,
                    "location": location,
                    "session_id": session_id
                }
                headers = {"x-worker-secret": os.getenv("WORKER_SECRET", "")}
                
                # TIMEOUT FIX: Increase to 300s (5 min) to match Cloud Run max
                resp = await client.post(f"{cloud_url}/api/worker/task", json=payload, headers=headers, timeout=300.0)
                
                if resp.status_code != 200:
                    print(f"❌ Cloud Dispatch Failed: {resp.text}")
                    await log("Cloud dispatch failed, running locally...", type="warning")
                else:
                    return # Successfully dispatched

        except httpx.ReadTimeout:
             # CRITICAL FIX: If it times out, it likely IS running on cloud, just taking long.
             # DONT run locally, just log and exit.
             print("⏳ Cloud Dispatch timed out waiting for response (Task likely running).")
             await log("Task dispatched to cloud (running in background)...", type="log")
             return

        except Exception as e:
             print(f"❌ Cloud Dispatch Error: {traceback.format_exc()}")
             await log(f"Cloud dispatch error: {e}, running locally...", type="warning")

    update_research_status(user_id, resume_filename, "SEARCHING", last_log="Starting local research...")

    try:
        # CANCELLATION CHECK
        if await check_cancellation(user_id, resume_filename): raise asyncio.CancelledError()

        # 1. Download Resume File
        remote_path = f"{user_id}/{resume_filename}"

        try:
            file_bytes = supabase_service.download_file(remote_path)
        except Exception as dl_error:
            print(f"❌ Failed to download resume: {dl_error}")
            update_research_status(user_id, resume_filename, "FAILED")
            return

        # Save temp for parsing
        await log("Downloading resume file...")
        import uuid
        tmp_id = str(uuid.uuid4())
        tmp_path = f"/tmp/{tmp_id}_{resume_filename}"

        with open(tmp_path, "wb") as f:
            f.write(file_bytes)

        # CANCELLATION CHECK
        if await check_cancellation(user_id, resume_filename): raise asyncio.CancelledError()

        # 2. Parse Resume (Dynamic)
        from app.utils.resume_parser import ResumeParser
        parser = ResumeParser(api_key=api_key)

        # Parse returns a JSON string, we need to load it
        await log("Parsing resume with Gemini 2.5 Flash...")
        parsed_json_str = await parser.parse_to_json(tmp_path)

        # Guard against Non-string return (e.g. None)
        if not parsed_json_str or not isinstance(parsed_json_str, str):
            print(f"⚠️ Parsing returned empty or invalid type: {type(parsed_json_str)}")
            profile_blob = {"raw_text": "Parsing Failed or Empty Response"}
        else:
            try:
                profile_blob = json.loads(parsed_json_str)
            except json.JSONDecodeError:
                # Fallback cleaning
                import re
                match = re.search(r'```json\n(.*?)\n```', parsed_json_str, re.DOTALL)
                if match:
                    profile_blob = json.loads(match.group(1))
                else:
                    profile_blob = {"raw_text": parsed_json_str} # Fallback

        # Clean up temp file
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass

        print(f"📄 Parsed Profile for {resume_filename}: {profile_blob.get('full_name', 'Unknown')}")

        # CANCELLATION CHECK
        if await check_cancellation(user_id, resume_filename): raise asyncio.CancelledError()

        # 3. Research
        print("🔎 Using Google Verification Agent...")
        await log(f"Searching Google for top {limit} jobs (this may take a moment)...")
        researcher = GoogleResearcherAgent(api_key=api_key)
             
        # We use the DYNAMIC profile_blob here
        leads = await researcher.gather_leads(profile_blob, limit=limit, job_title=job_title, location=location)

        # Prefix query_source for UI identification
        prefix = "GOOGLE"
        for lead in leads:
            lead['query_source'] = f"{prefix}|{lead.get('query_source', 'Unknown')}"

        # CANCELLATION CHECK
        if await check_cancellation(user_id, resume_filename): raise asyncio.CancelledError()

        # 4. Match
        await log(f"Found {len(leads)} raw leads. analyzing matches with Matcher Agent...")
        matcher = MatcherAgent(api_key=api_key)
        # Fix: Use the requested limit, not hardcoded 10
        scored_matches = await matcher.filter_and_score_leads(leads, profile_blob, limit=limit)

        # 5. Save Results
        # Save to Storage as JSON (Legacy Backup) & DB
        results_filename = f"matches_{resume_filename}.json"

        # Serialize
        json_bytes = json.dumps(scored_matches, indent=2).encode('utf-8')

        supabase_service.upload_file(
            file_content=json_bytes,
            file_name=results_filename,
            user_id=user_id,
            content_type="application/json"
        )

        # Save to DB
        supabase_service.save_leads_bulk(user_id, resume_filename, scored_matches)

        print(f"✅ Worker: Research Completed. Saved {len(scored_matches)} matches.")
        update_research_status(user_id, resume_filename, "COMPLETED")
        
        await log(f"Done! Found {len(scored_matches)} matches.", type="complete")
        if session_id:
            supabase_service.save_chat_message(session_id, "model", f"✅ Research Complete! Found **{len(scored_matches)}** matches.\n\nCheck the **Jobs** tab or reload your dashboard.")

    except asyncio.CancelledError:
        print(f"🛑 Worker: Research Cancelled for {resume_filename}")
        await log("Research cancelled by user.", type="error")
        if session_id:
            supabase_service.save_chat_message(session_id, "model", "🛑 Research Cancelled by user.")
        update_research_status(user_id, resume_filename, "CANCELLED")
        
    except Exception as e:
        print(f"❌ Worker: Research Failed: {e}")
        traceback.print_exc()
        if session_id:
            supabase_service.save_chat_message(session_id, "model", f"❌ Research Failed: {e}")
            
        # Ensure we update status to FAILED so UI unblocks
        try:
            update_research_status(user_id, resume_filename, "FAILED")
        except Exception as status_err:
             print(f"❌ Failed to final update status: {status_err}")


async def run_applier_task(job_url: str, resume_path: str, user_profile: dict, api_key: str, resume_filename: str = None, execution_mode: str = "local", session_id: int = None, instructions: str = None):
    print(f"🚀 Worker: Applying to {job_url} ...")
    
    async def log(msg, type="log"):
         if session_id: await log_stream_manager.broadcast(str(session_id), msg, type=type)

    if session_id:
        supabase_service.save_chat_message(session_id, "model", f"🚀 Starting Application to **{job_url}**...")
        await log(f"Initializing application agent for: {job_url}")

    # Resolve User ID early for dispatch
    user_id = user_profile.get("user_id") or user_profile.get("id")

    # Cloud Dispatch Check
    cloud_url = os.getenv("CLOUD_RUN_URL")
    # Only dispatch if we are not ALREADY in the cloud worker (prevent infinite loop if env vars are confusing)
    # But user_profile needs to be passed carefully.
    if cloud_url and not os.getenv("IS_CLOUD_WORKER") and execution_mode == 'cloud_run':
        import httpx
        print(f"🚀 Dispatching Applier task to Cloud Worker: {cloud_url}")
        await log("Dispatching Applier to Cloud Worker...")
        
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "type": "apply",
                    "user_id": user_id,
                    "job_url": job_url,
                    "resume_path": resume_path, # Note: This path is local, we might need to handle this differently for cloud. 
                    # actually worker endpoint logic below handles download. We pass resume_filename instead of path if possible?
                    # The worker needs to re-download. So we should pass resume_filename and user_id in payload, NOT local path.
                    "user_profile": user_profile,
                    "api_key": api_key,
                    "resume_filename": resume_filename,
                    "execution_mode": "local", # Worker runs it as local relative to itself (headless default), UNLESS we want worker to use managed?
                    # Actually if user wants Cloud Run + Managed Browser, we don't support that combo yet in UI.
                    # UI has "Google Cloud Run" (self-hosted) OR "Browser Use Cloud" (managed).
                    # "Google Cloud Run" implies self-hosted headless.
                    "session_id": session_id,
                    "instructions": instructions
                }
                headers = {"x-worker-secret": os.getenv("WORKER_SECRET", "")}
                # Increase timeout to 5 minutes to allow for full execution or at least long enough for initial steps
                resp = await client.post(f"{cloud_url}/api/worker/task", json=payload, headers=headers, timeout=300.0)
                if resp.status_code != 200:
                    print(f"❌ Cloud Dispatch Failed: {resp.text}")
                    # If user explicitly asked for Cloud, we should probably stop or notify rather than silently running local
                    # But for robustness, we can return Error status
                    await log(f"❌ Cloud Execution Failed (Status {resp.status_code}). Check Cloud Run logs.", type="error")
                    return "FAILED_DISPATCH"
                else:
                    return # Successfully dispatched
        except Exception as e:
             print(f"❌ Cloud Dispatch Error: {traceback.format_exc()}")
             await log(f"❌ Cloud Dispatch Error: {e}", type="error")
             return "FAILED_DISPATCH"

    # If we are here, we are running LOCALLY (or we are the worker)
    if execution_mode == 'cloud_run':
        # If we were supposed to be Cloud Run but fell through (unlikely with above returns), stop.
        return "FAILED_DISPATCH"

    # Resolve Lead ID for status updates
    # user_id already resolved above
    
    lead_id = None
    if user_id:
        # Use new method that handles fetch properly
        lead = supabase_service.get_lead_by_url(user_id, job_url)
        if lead:
            lead_id = lead['id']
            print(f"📋 Found Lead ID: {lead_id}")
            # Use specific ID update
            # Pass invalidation metadata if we have it
            supabase_service.update_lead_status(lead_id, "APPLYING", user_id=user_id, resume_filename=resume_filename, status_msg="Running Locally")
        else:
            print("⚠️ Could not find existing lead for this URL. Status updates will be skipped.")
    else:
        print("⚠️ No User ID found in profile. Cannot resolve lead.")

    try:
        # Detect environment for headless mode
        is_headless = os.getenv("HEADLESS", "false").lower() == "true"
        applier = ApplierAgent(api_key=api_key, headless=is_headless)
        
        # Determine Managed Browser (Browser Use Cloud) usage
        # STRICTLY enable only if requested via execution_mode
        if execution_mode == 'browser_use_cloud':
            use_managed_browser = True
        else:
            use_managed_browser = False
        
        await log(f"Launching browser (Headless={is_headless}, Managed Cloud={use_managed_browser})...")
        
        # Pass lead_id and instructions to apply method
        result_status = await applier.apply(job_url, user_profile, resume_path, lead_id=lead_id, use_managed_browser=use_managed_browser, session_id=session_id, instructions=instructions)
        
        print(f"🏁 Worker: Applier finished: {result_status}")
        
        await log(f"Application finished: {result_status}", type="complete")
        if session_id:
            supabase_service.save_chat_message(session_id, "model", f"🏁 Application Finished. Status: **{result_status}**")
        
        if lead_id:
             # Default to FAILED safest
             final_status = "FAILED"
             
             # 1. Trust JSON status if available and valid
             if isinstance(result_status, str) and result_status in ["APPLIED", "SUBMITTED", "SUCCESS"]:
                 final_status = "APPLIED"
             elif "Submitted" in str(result_status) or "Success" in str(result_status):
                 final_status = "APPLIED"
             
             # 2. Overrule if explicit failure is detected
             if "FAIL" in str(result_status).upper() or "ERROR" in str(result_status).upper() or "COULD NOT BE FULLY COMPLETED" in str(result_status).upper():
                 final_status = "FAILED"
                 
             if "DryRun" in str(result_status): final_status = "DRY_RUN"
             
             print(f"✅ Final Status Verdict: {final_status}")
             supabase_service.update_lead_status(lead_id, final_status, user_id=user_id, resume_filename=resume_filename)

    except asyncio.CancelledError:
        print(f"🛑 Worker: Applier Cancelled for {job_url}")
        if session_id:
            supabase_service.save_chat_message(session_id, "model", "🛑 Application Cancelled by user.")
        if lead_id:
            supabase_service.update_lead_status(lead_id, "CANCELLED", user_id=user_id, resume_filename=resume_filename)

    except Exception as e:
        print(f"❌ Worker: Applier Failed: {e}")
        if lead_id:
            supabase_service.update_lead_status(lead_id, "FAILED", user_id=user_id, resume_filename=resume_filename)
