import asyncio
import os
import json
from dotenv import load_dotenv
from utils.resume_parser import ResumeParser

load_dotenv()

async def main():
    parser = ResumeParser(api_key=os.environ.get("GEMINI_API_KEY"))

    # Update this path to your actual resume file!
    resume_path = "data/jc-resume-2025.pdf"

    if not os.path.exists(resume_path):
        print(f"❌ Resume not found at {resume_path}. Please add it.")
        return

    print("📄 Parsing resume...")
    profile_json = await parser.parse_to_json(resume_path)

    # Save it so we can use it later without calling the API again
    with open("data/profile.json", "w") as f:
        f.write(profile_json)

    print("✅ Profile saved to data/profile.json!")
    print(json.dumps(json.loads(profile_json), indent=2))

if __name__ == "__main__":
    asyncio.run(main())
