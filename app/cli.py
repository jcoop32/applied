import asyncio
import argparse
import json
import os
import sys
import logging

# Ensure app can be imported
sys.path.append(os.getcwd())

from app.services.agent_runner import run_research_pipeline, run_applier_task
from app.services.supabase_client import supabase_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cli")

async def main():
    parser = argparse.ArgumentParser(description="Applied Agent CLI")
    parser.add_argument("--task", type=str, required=True, choices=["research", "apply"], help="Task to run")
    parser.add_argument("--payload", type=str, required=True, help="JSON payload string")

    args = parser.parse_args()

    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload")
        sys.exit(1)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        sys.exit(1)

    try:
        if args.task == "research":
            user_id = payload.get("user_id")
            resume_filename = payload.get("resume_filename")
            limit = payload.get("limit", 20)
            job_title = payload.get("job_title")
            location = payload.get("location")
            job_title = payload.get("job_title")
            location = payload.get("location")
            session_id = payload.get("session_id")

            if not user_id or not resume_filename:
                logger.error("Missing user_id or resume_filename")
                sys.exit(1)

            logger.info(f"Starting Research Task: User={user_id}, Resume={resume_filename}, Limit={limit}, Title={job_title}, Loc={location}, Session={session_id}, Type=Google")
            await run_research_pipeline(user_id, resume_filename, api_key, limit, job_title, location, session_id=session_id)

        elif args.task == "apply":
            user_id = payload.get("user_id") # Needed for resume path construction if redundant
            job_url = payload.get("job_url")
            # In API we downloaded resume to tmp.
            # Here we should probably do the same logic or let run_applier_task handle it?
            # run_applier_task (in agent_runner) accepts a LOCAL resume_path.
            # So we must download it here first.

            resume_filename = payload.get("resume_filename")
            user_profile = payload.get("user_profile", {}) # Expecting profile blob or email/name
            user_profile["user_id"] = user_id # Ensure ID is passed for lead lookup


            if not user_id or not job_url or not resume_filename:
                 logger.error("Missing user_id, job_url, or resume_filename")
                 sys.exit(1)

            # Download Resume Logic
            # (Duplicated from API logic, but safer here)
            logger.info(f"Downloading resume for Application: {resume_filename}")

            try:
                remote_path = f"{user_id}/{resume_filename}"
                file_bytes = supabase_service.download_file(remote_path)

                import uuid
                tmp_id = str(uuid.uuid4())
                tmp_path = f"/tmp/{tmp_id}_{resume_filename}"

                with open(tmp_path, "wb") as f:
                    f.write(file_bytes)

                logger.info(f"Starting Apply Task: URL={job_url}")
                await run_applier_task(job_url, tmp_path, user_profile, api_key, resume_filename=resume_filename)

                # Cleanup
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

            except Exception as e:
                logger.error(f"Failed to prepare application context: {e}")
                sys.exit(1)


    except Exception as e:
        logger.error(f"Global CLI Error: {e}")
        # Try to update status if we have context
        try:
             # We might have args parsed
             if 'payload' in locals() and isinstance(payload, dict):
                 user_id = payload.get("user_id")
                 resume_filename = payload.get("resume_filename")
                 if user_id and resume_filename:
                     from app.services.agent_runner import update_research_status
                     logger.info("Attempting to set status to FAILED...")
                     update_research_status(user_id, resume_filename, "FAILED")
        except Exception as cleanup_err:
             logger.error(f"Failed to cleanup status: {cleanup_err}")

        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
