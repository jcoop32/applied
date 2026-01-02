import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BUCKET_NAME = "resumes"

class SupabaseService:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("⚠️ Warning: SUPABASE_URL or SUPABASE_KEY not found in .env")
            self.client = None
        else:
            self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    def upload_resume(self, file_content: bytes, file_name: str, user_id: int, content_type: str = "application/pdf") -> str:
        """
        Uploads a resume to the user's folder in the bucket: user_id/filename
        Returns the public URL.
        """
        if not self.client:
             raise Exception("Supabase client not initialized")

        path = f"{user_id}/{file_name}"

        try:
            # Attempt upload
            self.client.storage.from_(BUCKET_NAME).upload(
                path=path,
                file=file_content,
                file_options={"content-type": content_type, "upsert": "true"}
            )

            public_url = self.client.storage.from_(BUCKET_NAME).get_public_url(path)
            return public_url

        except Exception as e:
            # Check for "Bucket not found" error string
            error_str = str(e)
            if "Bucket not found" in error_str or "404" in error_str:
                print(f"⚠️ Bucket '{BUCKET_NAME}' not found. Attempting to create...")
                try:
                    self.client.storage.create_bucket(BUCKET_NAME, options={"public": True})
                    print(f"✅ Bucket '{BUCKET_NAME}' created successfully.")

                    # Retry upload
                    self.client.storage.from_(BUCKET_NAME).upload(
                        path=path,
                        file=file_content,
                        file_options={"content-type": content_type, "upsert": "true"}
                    )
                    public_url = self.client.storage.from_(BUCKET_NAME).get_public_url(path)
                    return public_url
                except Exception as create_error:
                    print(f"❌ Failed to create/upload to bucket: {create_error}")
                    raise e

            print(f"❌ Supabase Upload Error: {e}")
            raise e

    def list_resumes(self, user_id: int):
        """
        Lists resumes in the user's specific folder.
        """
        if not self.client:
             return []

        try:
            # List files in the folder "user_id/"
            files = self.client.storage.from_(BUCKET_NAME).list(path=f"{user_id}")

            result = []
            for f in files:
                if f['name'] == '.emptyFolderPlaceholder': continue # Skip system files

                result.append({
                    "name": f['name'],
                    "id": f['id'],
                    "created_at": f.get('created_at'),
                    "metadata": f.get('metadata'),
                    "url": self.client.storage.from_(BUCKET_NAME).get_public_url(f"{user_id}/{f['name']}")
                })
            return result
        except Exception as e:
            print(f"❌ Supabase List Error: {e}")
            return []

    def get_credentials(self, email: str):
        """
        Fetches credentials for a specific email from the 'credentials' table.
        """
        if not self.client:
            print("⚠️ Supabase client not initialized.")
            return []

        try:
            response = self.client.table("credentials").select("*").eq("email", email).execute()
            return response.data
        except Exception as e:
            print(f"❌ Supabase Credential Fetch Error: {e}")
            return []

    def save_credential(self, domain: str, email: str, password: str, user_id: int = None):
        """
        Saves or updates a credential in the 'credentials' table.
        """
        if not self.client:
             print("⚠️ Supabase client not initialized.")
             return

        try:
            data = {
                "domain": domain,
                "email": email,
                "password": password,
                "user_id": user_id
            }
            # Upsert on email/domain
            self.client.table("credentials").upsert(data, on_conflict="email, domain").execute()
            print(f"✅ Saved credential for {domain} to DB.")
        except Exception as e:
            print(f"❌ Supabase Credential Save Error: {e}")

    # --- User Management ---
    def get_user_by_email(self, email: str):
        """
        Fetches a user by email from the 'users' table.
        """
        if not self.client:
            return None

        try:
            response = self.client.table("users").select("*").eq("email", email).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"❌ Supabase User Fetch Error: {e}")
            return None

    def create_user(self, email: str, password_hash: str, full_name: str = None):
        """
        Creates a new user in the 'users' table.
        """
        if not self.client:
            raise Exception("Supabase client not initialized")

        try:
            data = {
                "email": email,
                "password_hash": password_hash,
                "full_name": full_name
            }
            response = self.client.table("users").insert(data).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"❌ Supabase User Create Error: {e}")
            # Likely duplicate email error
            raise e

    def update_user_profile(self, user_id: int, data: dict):
        """
        Updates the user's profile data (e.g. primary_resume_name, profile_data).
        """
        if not self.client:
            raise Exception("Supabase client not initialized")

        try:
            response = self.client.table("users").update(data).eq("id", user_id).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"❌ Supabase User Update Error: {e}")
            raise e

    def download_file(self, path: str) -> bytes:
        """
        Downloads a file from the bucket as bytes.
        """
        if not self.client:
            raise Exception("Supabase client not initialized")

        try:
            response = self.client.storage.from_(BUCKET_NAME).download(path)
            # response is bytes directly in some versions, or needs .read()
            return response
        except Exception as e:
            print(f"❌ Supabase Download Error: {e}")
            raise e

    def delete_file(self, path: str):
        """
        Deletes a file from the bucket.
        """
        if not self.client:
             raise Exception("Supabase client not initialized")

        try:
            self.client.storage.from_(BUCKET_NAME).remove([path])
            return True
        except Exception as e:
             print(f"❌ Supabase Delete Error: {e}")
             raise e

# Singleton instance
supabase_service = SupabaseService()
