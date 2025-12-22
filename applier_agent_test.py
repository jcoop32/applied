import asyncio
import os
from dotenv import load_dotenv
from agents.applier import ApplierAgent

# Dummy Profile for testing
TEST_PROFILE = {
    "name": "Joshua Cooper",
    "email": "agenttest3@sandjexpress.space", # Use a safe test email
    "phone": "224-245-8826",
    "linkedin": "linkedin.com/in/joshuacooper-test",
    "github": "github.com/jcoop32",
    "portfolio": "joshuacooper.dev",
    "salary_expectations": "$120,000",
    "location": "Remote",
    "education": [
        {
            "degree": "B.S. Computer Science",
            "school": "University of Illinois at Chicago",
            "year": "2022-2024"
        }
    ],
    "experience": [
        {
            "title": "Software Engineer",
            "company": "Tech Corp",
            "duration": "2 years",
            "description": "Built web apps."
        }
    ]
}

async def test_applier():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("❌ Error: GEMINI_API_KEY not found in .env")
        return

    agent = ApplierAgent(api_key=api_key)

    # 1. Ask user for a URL to test (or hardcode one for dev)
    print("\n🧪 Applier Agent Test Script")
    print("----------------------------")
    url = input("Enter a Job Application URL to test (Dry Run): ").strip()

    if not url:
        print("⚠️ No URL provided. Exiting.")
        return

    # 2. Path to a dummy resume (ensure one exists or point to main one)
    resume_path = "data/jc-resume-2025.pdf"
    if not os.path.exists(resume_path):
        print(f"⚠️ Warning: Resume not found at {resume_path}. Please ensure it exists.")
        # Create a dummy file if needed? No, user should have it.
        return

    print(f"\n🚀 Starting Dry Run Application to: {url}")
    print(f"👤 Using Profile: {TEST_PROFILE['email']}")

    # 3. Run Apply
    result = await agent.apply(url, TEST_PROFILE, resume_path, dry_run=True)

    print("\n🏁 Validation Result:")
    print(result)

    # Check credentials
    if os.path.exists("data/credentials.json"):
        print("\n🔐 Credentials File Content:")
        with open("data/credentials.json", "r") as f:
            print(f.read())

if __name__ == "__main__":
    asyncio.run(test_applier())
