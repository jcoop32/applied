# import asyncio
# import os
# from dotenv import load_dotenv
# from agents.verifier import VerifierAgent

# load_dotenv()

# async def main():
#     api_key = os.getenv("GEMINI_API_KEY")
#     verifier = VerifierAgent(api_key=api_key)

#     # Test with a link found by your researcher
    # test_url = "https://job-boards.eu.greenhouse.io/imc/jobs/4704842101"
    # test_url = "https://job-boards.greenhouse.io/drw?error=true"
    # test_url = "https://job-boards.greenhouse.io/imc?error=true"


#     print(f"🚀 Starting verification test...")
#     result = await verifier.verify_link(test_url)

#     print("\n--- Verification Result ---")
#     print(f"Valid Job Post: {result['is_valid']}")
#     print(f"Apply Button Found: {result['has_apply_button']}")
#     print(f"Reason: {result['reason']}")
#     if "screenshot_path" in result:
#         print(f"📸 Screenshot saved to: {result['screenshot_path']}")

# if __name__ == "__main__":
#     asyncio.run(main())

import asyncio
import os
import json
from dotenv import load_dotenv
from agents.verifier import VerifierAgent

load_dotenv()

async def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not found.")
        return

    verifier = VerifierAgent(api_key=api_key)

    # Test URLs - mix of valid and likely invalid/error pages
    test_urls = [
        "https://job-boards.eu.greenhouse.io/imc/jobs/4704842101", # Likely Valid
        "https://job-boards.greenhouse.io/drw?error=true", # Error/Invalid
        "https://www.google.com" # Not a job board
    ]

    print(f"🚀 Starting verification tests for {len(test_urls)} URLs...")

    for url in test_urls:
        print(f"\n🔎 Verifying: {url}")
        try:
            result = await verifier.verify_link(url)

            print("-" * 40)
            print("VERIFICATION RESULT")
            print("-" * 40)
            print(f"URL: {result.get('url', 'N/A')}")
            print(f"Is Valid Job: {result.get('is_valid')}")
            print(f"Has Apply Button: {result.get('has_apply_button')}")
            print(f"Job Title: {result.get('job_title')}")
            print(f"Reason: {result.get('reason')}")
            print("-" * 40)

        except Exception as e:
            print(f"❌ Error testing URL {url}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
