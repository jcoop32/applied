import asyncio
import os
from dotenv import load_dotenv
from app.agents.applier import ApplierAgent

# Dummy Profile for testing
TEST_PROFILE = {
    "name": "Joshua Cooper",
    "email": "agenttest14@sandjexpress.space", # Use a safe test email
    "phone": "224-245-8826",
    "linkedin": "linkedin.com/in/joshuacooper-test",
    "github": "github.com/jcoop32",
    "portfolio": "joshuacooper.dev",
    "salary_expectations": "$120,000",
    "location": "Chicago, IL",
    "Address": "123 Main St, Chicago, IL 60601",
    "Voluntary Questions Answers": {
        "Race": "Black or African American",
        "Gender": "Male",
        "Veteran Status": "No",
        "Disability Status": "No"
    },
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
        # Graceful fallback for test environment
        print(f"⚠️ Warning: Resume not found at {resume_path}. Creating a dummy one.")
        with open(resume_path, "w") as f:
            f.write("Dummy Resume Content")

    print(f"\n🚀 Starting Dry Run Application to: {url}")
    print(f"👤 Using Profile: {TEST_PROFILE['email']}")

    # 3. Test Resolution ONLY first
    print("\n🕵️ Testing Resolution Logic...")
    try:
        resolved = await agent._resolve_application_url(url)
        print(f"✅ Final Resolved URL: {resolved}")
    except Exception as e:
        print(f"❌ Resolution Failed: {e}")
        return

    # Skip full browser apply for this specific verification step unless user wants it
    # We really just want to prove the redirect chaser works.
    print("\n(Skipping full browser apply for this investigation step)")
    
    # Clean up dummy resume if we created it
    # if os.path.exists(resume_path) and os.path.getsize(resume_path) < 100:
    #     os.remove(resume_path)

if __name__ == "__main__":
    asyncio.run(test_applier())
