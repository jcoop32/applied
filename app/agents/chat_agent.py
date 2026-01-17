import os
import json
from google import genai
from app.services.supabase_client import supabase_service

class ChatAgent:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model_id = 'gemini-2.0-flash-exp' # Using Flash for speed/cost

    async def generate_response(self, user_id: int, message: str, history: list) -> str:
        """
        Generates a response from the "Resume Expert" persona.
        """
        # 1. Fetch User Context (Profile, Research Status, etc.)
        # We want the agent to be aware of what's happening.
        user_data = supabase_service.get_user_by_email(email=None) # We don't have email directly here readily without lookup, but we have user_id.
        # Wait, supabase_service.get_user_by_email needs email.
        # Let's fix supabase_service to get by ID or just fetch research status.
        
        # Actually, let's just fetch the 'profile_data' which contains the resume text usually?
        # In this app, it seems 'profile_data' in 'users' table holds parsed info.
        
        # Let's get the profile data.
        profile_data = supabase_service.get_research_status(user_id) # Returns dict of profile_data
        
        # Also get recent leads counts?
        # existing_leads = supabase_service.get_lead_counts(user_id) 
        # (This might be too heavy if they have thousands, let's skip for now or make lightweight)

        # 2. Construct System Prompt
        context_str = "User Profile Data:\n" + json.dumps(profile_data, indent=2)
        
        system_instruction = f"""
        You are the "Resume Expert" AI Assistant for the 'Applied' Job Automation Platform.
        
        Your Capabilities:
        1. **Analyze Resumes**: You can discuss the user's resume strengths/weaknesses based on their profile data.
        2. **Explain Agents**:
           - "Researcher Agent": Scans ATS sites (Greenhouse, Lever, etc.) for jobs.
           - "Applier Agent": Can apply to jobs automatically (or via GitHub Actions).
        3. **Job Search Advice**: Give tips on keywords, Boolean search strings, etc.
        
        Context:
        {context_str}
        
        Tone: Professional, Encouraging, Concise.
        
        Instructions:
        - If the user asks to "Find jobs", tell them to click the "Researcher" chip/button in the UI.
        - If the user asks to "Apply", explain they can click "Apply" on any job card.
        - Keep answers short (under 3 paragraphs) unless analyzing a resume deeply.
        - Format output with Markdown.
        """

        # 3. Format History for Gemini
        # Gemini Client SDK expects specific format or we can just concat.
        # Let's use the chat session feature if possible, or just append messages.
        # for simplicity with this client, we can send `contents`.
        
        contents = []
        contents.append(genai.types.Content(
            role="model",
            parts=[genai.types.Part.from_text(text=system_instruction)] # System instruction as first model msg or system? 
            # SDK 2.0 uses 'config' for system instruction usually, or we can just prepend user/model.
            # Let's use config 'system_instruction' if available in generate_content, 
            # but for Chat sessions, it's usually set on start_chat.
        ))
        
        # Reconstruct history
        for msg in history:
            role = "user" if msg['role'] == 'user' else "model"
            contents.append(genai.types.Content(
                role=role, 
                parts=[genai.types.Part.from_text(text=msg['content'])]
            ))
            
        # Add current message
        contents.append(genai.types.Content(
            role="user",
            parts=[genai.types.Part.from_text(text=message)]
        ))

        try:
            # We use the generate_content for one-off stateless (with history manually passed)
            # OR we can use built-in system_instruction if supported.
            # simpler to just prepend system prompt text content for now in 1.5/2.0 flash unless strict.
            
            # Let's try the modern way
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_instruction
                )
            )
            return response.text
        except Exception as e:
            print(f"Gemini Chat Error: {e}")
            return "I'm having trouble connecting to my brain right now. Please try again."
