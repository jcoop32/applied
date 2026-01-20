
import os
import json
import logging
import asyncio
from app.services.supabase_client import supabase_service
from app.services.log_stream import log_stream_manager

from app.agents.google_researcher import GoogleResearcherAgent
from app.agents.matcher import MatcherAgent
from app.agents.applier import ApplierAgent

logger = logging.getLogger(__name__)

def update_research_status(user_id: int, resume_filename: str, status: str):
    """
    Updates the 'research_status' in the user's profile_data.
    States: IDLE, QUEUED, SEARCHING, COMPLETED, FAILED
    """
    try:
        response = supabase_service.client.table("users").select("profile_data").eq("id", user_id).execute()
        if not response.data:
            return

        current_data = response.data[0].get("profile_data") or {}
        if "research_status" not in current_data:
            current_data["research_status"] = {}

        current_data["research_status"][resume_filename] = {
            "status": status,
            "updated_at": str(os.times())
        }

        supabase_service.update_user_profile(user_id, {"profile_data": current_data})

    except Exception as e:
        logger.error(f"Failed to update research status: {e}")


async def run_research_pipeline(user_id: int, resume_filename: str, api_key: str, limit: int = 20, job_title: str = None, location: str = None, session_id: int = None):
    print(f"🕵️ Worker: Starting Research for {resume_filename} with limit {limit} (Type: Google)...")
    if session_id:
        supabase_service.save_chat_message(session_id, "model", f"fe0f Starting Research for **{resume_filename}**...")
        await log_stream_manager.broadcast(str(session_id), f"Starting research pipeline for {resume_filename}...")
    
    update_research_status(user_id, resume_filename, "SEARCHING")

    try:
        # 1. Download Resume File
        remote_path = f"{user_id}/{resume_filename}"

        try:
            file_bytes = supabase_service.download_file(remote_path)
        except Exception as dl_error:
            print(f"❌ Failed to download resume: {dl_error}")
            update_research_status(user_id, resume_filename, "FAILED")
            return

        # Save temp for parsing
        if session_id: await log_stream_manager.broadcast(str(session_id), "Downloading resume file...")
        import uuid
        tmp_id = str(uuid.uuid4())
        tmp_path = f"/tmp/{tmp_id}_{resume_filename}"

        with open(tmp_path, "wb") as f:
            f.write(file_bytes)

        # 2. Parse Resume (Dynamic)
        from app.utils.resume_parser import ResumeParser
        parser = ResumeParser(api_key=api_key)

        # Parse returns a JSON string, we need to load it
        if session_id: await log_stream_manager.broadcast(str(session_id), "Parsing resume with Gemini 2.5 Flash...")
        parsed_json_str = await parser.parse_to_json(tmp_path)

        # Guard against Non-string return (e.g. None)
        if not parsed_json_str or not isinstance(parsed_json_str, str):
            print(f"⚠️ Parsing returned empty or invalid type: {type(parsed_json_str)}")
            # Try to recover or fail
            # Just create a minimal blob so we don't crash
            profile_blob = {"raw_text": "Parsing Failed or Empty Response"}
            # OR fail? If parsing fails, research is garbage.
            # Let's try to proceed with minimal info if possible, but usually this is fatal.
            # But earlier fallback code exists.
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

        # 3. Research
        print("🔎 Using Google Verification Agent...")
        if session_id: await log_stream_manager.broadcast(str(session_id), f"Searching Google for top {limit} jobs (this may take a moment)...")
        researcher = GoogleResearcherAgent(api_key=api_key)
             
        # We use the DYNAMIC profile_blob here
        leads = await researcher.gather_leads(profile_blob, limit=limit, job_title=job_title, location=location)

        # Prefix query_source for UI identification
        prefix = "GOOGLE"
        for lead in leads:
            lead['query_source'] = f"{prefix}|{lead.get('query_source', 'Unknown')}"

        # 4. Match
        if session_id: await log_stream_manager.broadcast(str(session_id), f"Found {len(leads)} raw leads. analyzing matches with Matcher Agent...")
        matcher = MatcherAgent(api_key=api_key)
        scored_matches = await matcher.filter_and_score_leads(leads, profile_blob, limit=10)

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
        
        if session_id:
            await log_stream_manager.broadcast(str(session_id), f"Done! Found {len(scored_matches)} matches.", type="complete")
            supabase_service.save_chat_message(session_id, "model", f"✅ Research Complete! Found **{len(scored_matches)}** matches.\n\nCheck the **Jobs** tab or reload your dashboard.")

    except asyncio.CancelledError:
        print(f"🛑 Worker: Research Cancelled for {resume_filename}")
        if session_id:
            await log_stream_manager.broadcast(str(session_id), "Research cancelled by user.", type="error")
            supabase_service.save_chat_message(session_id, "model", "🛑 Research Cancelled by user.")
        update_research_status(user_id, resume_filename, "CANCELLED")
        
    except Exception as e:
        print(f"❌ Worker: Research Failed: {e}")
        if session_id:
            supabase_service.save_chat_message(session_id, "model", f"❌ Research Failed: {e}")
            
        # Ensure we update status to FAILED so UI unblocks
        try:
            update_research_status(user_id, resume_filename, "FAILED")
        except Exception as status_err:
             print(f"❌ Failed to final update status: {status_err}")


async def run_applier_task(job_url: str, resume_path: str, user_profile: dict, api_key: str, resume_filename: str = None, use_cloud: bool = False, session_id: int = None, instructions: str = None):
    print(f"🚀 Worker: Applying to {job_url} ...")
    if session_id:
        supabase_service.save_chat_message(session_id, "model", f"🚀 Starting Application to **{job_url}**...")
        await log_stream_manager.broadcast(str(session_id), f"Initializing application agent for: {job_url}")
    
    # Resolve Lead ID for status updates
    user_id = user_profile.get("user_id") or user_profile.get("id")
    
    lead_id = None
    if user_id:
        # Use new method that handles fetch properly
        lead = supabase_service.get_lead_by_url(user_id, job_url)
        if lead:
            lead_id = lead['id']
            print(f"📋 Found Lead ID: {lead_id}")
            # Use specific ID update
            # Pass invalidation metadata if we have it
            supabase_service.update_lead_status(lead_id, "APPLYING", user_id=user_id, resume_filename=resume_filename)
        else:
            print("⚠️ Could not find existing lead for this URL. Status updates will be skipped.")
    else:
        print("⚠️ No User ID found in profile. Cannot resolve lead.")

    try:
        # Detect environment for headless mode
        is_headless = os.getenv("HEADLESS", "false").lower() == "true" or os.getenv("GITHUB_ACTIONS") == "true"
        applier = ApplierAgent(api_key=api_key, headless=is_headless)
        if session_id: await log_stream_manager.broadcast(str(session_id), f"Launching browser (Headless={is_headless}, Cloud={use_cloud})...")
        
        # Pass lead_id and instructions to apply method
        result_status = await applier.apply(job_url, user_profile, resume_path, lead_id=lead_id, use_cloud=use_cloud, session_id=session_id, instructions=instructions)
        
        print(f"🏁 Worker: Applier finished: {result_status}")
        
        if session_id:
            await log_stream_manager.broadcast(str(session_id), f"Application finished: {result_status}", type="complete")
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
