import os
import json
import logging
import httpx

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO_OWNER = os.getenv("GITHUB_REPO_OWNER")
GITHUB_REPO_NAME = os.getenv("GITHUB_REPO_NAME")
# We'll allow checking this flag here or in the caller, but usually caller decides.
# USE_GITHUB_ACTIONS is a policy flag, not a capability flag, but we can read it.

async def dispatch_github_action(workflow_file: str, task: str, payload: dict):
    if not GITHUB_TOKEN or not GITHUB_REPO_OWNER or not GITHUB_REPO_NAME:
        logger.warning(f"GitHub configuration missing (Token={bool(GITHUB_TOKEN)}, Owner={GITHUB_REPO_OWNER}, Repo={GITHUB_REPO_NAME}). failing dispatch.")
        return False

    url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/actions/workflows/{workflow_file}/dispatches"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Payload must be a string for the input
    data = {
        "ref": "main", # Or current branch? Ideally env var or default main
        "inputs": {
            "task": task,
            "payload": json.dumps(payload)
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            if response.status_code != 204:
                logger.error(f"Failed to dispatch GitHub Action {workflow_file}: {response.status_code} {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error dispatching GitHub Action: {e}")
            return False

    return True
