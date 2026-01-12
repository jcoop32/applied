import sys
import os
import json
import uuid

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.supabase_client import supabase_service

def test_profile_update():
    # 1. Create a unique test user
    email = f"test_profile_{uuid.uuid4()}@example.com"
    print(f"Creating user: {email}")
    
    try:
        user = supabase_service.create_user(email, "hashed_password", "Test User")
        print(f"User created with ID: {user['id']}")
    except Exception as e:
        print(f"Failed to create user: {e}")
        return

    user_id = user['id']

    # 2. Define the payload with new structure
    payload = {
      "skills": [
        "Python",
        "Typescript"
      ],
      "summary": "Test Summary",
      "education": [
        {
          "school": "Test University",
          "degree": "BS CS",
          "start_year": "2023",
          "end_year": "2026",
          "start_month": "January",
          "end_month": "May",
          "date": "Jan 2023 - May 2026"
        }
      ],
      "experience": [
        {
          "company": "Test Corp",
          "title": "Intern",
          "start_year": "2024",
          "end_year": "2024",
          "start_month": "June",
          "end_month": "August",
          "is_current": False,
          "duration": "Jun 2024 - Aug 2024",
          "description": "Did things."
        }
      ],
      "contact_info": {
        "phone": "555-555-5555"
      },
      "demographics": {
        "race": "Test",
        "veteran": "No"
      },
      "salary_expectations": "$100k"
    }

    # 3. Update profile
    print("Updating profile with new structure...")
    update_data = {"profile_data": payload}
    updated_user = supabase_service.update_user_profile(user_id, update_data)
    
    # 4. Verify data was saved
    print("Verifying saved data...")
    saved_profile = updated_user.get('profile_data', {})
    
    # Check key fields
    education = saved_profile.get('education', [])
    if not education:
        print("FAIL: Education array is empty")
    else:
        edu_item = education[0]
        if edu_item.get('start_year') == "2023":
            print("PASS: start_year saved correctly in education")
        else:
            print(f"FAIL: start_year mismatch. Got: {edu_item.get('start_year')}")

    experience = saved_profile.get('experience', [])
    if not experience:
        print("FAIL: Experience array is empty")
    else:
        exp_item = experience[0]
        if exp_item.get('start_year') == "2024":
            print("PASS: start_year saved correctly in experience")
        else:
            print(f"FAIL: start_year mismatch. Got: {exp_item.get('start_year')}")

    # Clean up (Optional, but good practice in real tests, here we just leave it)

if __name__ == "__main__":
    test_profile_update()
