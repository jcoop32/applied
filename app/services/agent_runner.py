
import os
import json
import logging
import asyncio
from app.services.supabase_client import supabase_service
from app.agents.researcher import ResearcherAgent
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


async def run_research_pipeline(user_id: int, resume_filename: str, api_key: str, limit: int = 20):
    print(f"🕵️ Worker: Starting Research for {resume_filename} with limit {limit}...")
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
        import uuid
        tmp_id = str(uuid.uuid4())
        tmp_path = f"/tmp/{tmp_id}_{resume_filename}"

        with open(tmp_path, "wb") as f:
            f.write(file_bytes)

        # 2. Parse Resume (Dynamic)
        from app.utils.resume_parser import ResumeParser
        parser = ResumeParser(api_key=api_key)

        # Parse returns a JSON string, we need to load it
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
        researcher = ResearcherAgent(api_key=api_key)
        # We use the DYNAMIC profile_blob here
        leads = await researcher.gather_leads(profile_blob, limit=limit)

        # 4. Match
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

    except Exception as e:
        print(f"❌ Worker: Research Failed: {e}")
        # Ensure we update status to FAILED so UI unblocks
        try:
            update_research_status(user_id, resume_filename, "FAILED")
        except Exception as status_err:
             print(f"❌ Failed to final update status: {status_err}")

async def run_applier_task(job_url: str, resume_path: str, user_profile: dict, api_key: str):
    print(f"🚀 Worker: Applying to {job_url} ...")
    try:
        applier = ApplierAgent(api_key=api_key)
        # ApplierAgent should handle headless mode internally or via config
        result_status = await applier.apply(job_url, user_profile, resume_path)
        print(f"🏁 Worker: Applier finished: {result_status}")
    except Exception as e:
        print(f"❌ Worker: Applier Failed: {e}")
