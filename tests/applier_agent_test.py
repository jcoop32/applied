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
    # url = input("Enter a Job Application URL to test (Dry Run): ").strip()
    url = "https://www.getwork.com/details/5487527524?v=3709C5FEF60F62B80D4B94C89F0676048F47DAFD"
    
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
    
    # DEBUG: Fetch and inspect the SOURCE page content first
    import requests
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
    try:
        print(f"\n🔍 DEBUG: Fetching source URL: {url}")
        r_src = requests.get(url, headers=headers, timeout=10)
        print(f"Source Status: {r_src.status_code}")
        if "greenhouse" in r_src.text or "lever" in r_src.text:
            print("✅ FOUND target words (greenhouse/lever) in SOURCE body!")
            for line in r_src.text.splitlines():
                 if "greenhouse" in line or "lever" in line:
                     print(f"SOURCE MATCH: {line.strip()[:200]}")
        else:
            print("❌ 'greenhouse/lever' NOT found in SOURCE body.")
    except Exception as e:
        print(f"⚠️ Source fetch failed: {e}")

    # 3. Test Resolution ONLY first
    print("\n🕵️ Testing Resolution Logic...")
    try:
        resolved = await agent._resolve_application_url(url)
        print(f"✅ Final Resolved URL: {resolved}")
        
        # DEBUG: Inspect the content of the resolved URL if it's still Adzuna
        if "adzuna" in resolved:
            print("\n🔍 DEBUG: Inspecting stuck URL content...")
            import requests
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }
            r = requests.get(resolved, headers=headers)
            print(f"Status: {r.status_code}")
            
            # Check if the known target (Greenhouse) is in the text
            if "greenhouse" in r.text or "lever" in r.text:
                 print("✅ FOUND target words in body! Extraction possible.")
                 for line in r.text.splitlines():
                     if "greenhouse" in line or "lever" in line:
                         print(f"MATCH: {line.strip()[:200]}...") # Truncate long lines
            else:
                 print("❌ 'greenhouse/lever' NOT found in body.")
            
            # Print potential JS redirects
            if "window.location" in r.text:
                print("⚠️ Found 'window.location' in body. Inspecting:")
                for line in r.text.splitlines():
                    if "window.location" in line:
                         print(f"JS MATCH: {line.strip()[:300]}")
            
            print(f"Content Preview: {r.text[:2000]}")

    except Exception as e:
        print(f"❌ Resolution Failed: {e}")
        return

    # Skip full apply
    print("\n(Skipping full browser apply for this investigation step)")

if __name__ == "__main__":
    asyncio.run(test_applier())
