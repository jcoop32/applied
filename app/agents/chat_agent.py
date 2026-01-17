import os
import json
from typing import List
from google import genai
from app.services.supabase_client import supabase_service

class ChatAgent:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model_id = 'gemini-2.0-flash-exp' # Using Flash for speed/cost

    async def generate_response(self, user_id: int, message: str, history: list, available_resumes: list = []) -> dict:
        """
        Generates a response from the "Resume Expert" persona.
        Returns a dict: { "role": "model", "content": str, "action": dict|None }
        """
        # 1. Fetch User Context (Profile, Research Status, etc.)
        profile_data = supabase_service.get_research_status(user_id) # Returns dict of profile_data
        
        # 2. Construct System Prompt
        context_str = "User Profile Data:\n" + json.dumps(profile_data, indent=2)
        resumes_str = ", ".join(available_resumes) if available_resumes else "No resumes uploaded."

        system_instruction = f"""
        You are the "Resume Expert" AI Assistant for the 'Applied' Job Automation Platform.
        
        Your Capabilities:
        1. **Analyze Resumes**: You can discuss the user's resume strengths/weaknesses based on their profile data.
        2. **Find Jobs**: You can search for jobs using the `search_jobs` tool. Use the exact resume filename from the available list.
           - If the user has multiple resumes and doesn't specify which to use, ASK CLARIFICATION first.
           - If the user has only one resume, default to it.
        3. **Apply to Jobs**: You can start an application using the `apply_to_job` tool.
        
        Context:
        {context_str}
        
        Available Resumes for Tools: [{resumes_str}]
        
        Tone: Professional, Encouraging, Concise.
        
        Instructions:
        You are the "Resume Expert" AI. You help users find and apply to jobs.
        
        **CRITICAL: TOOL USAGE RULES**
        1. **Find Jobs / Search**:
           - IF the user wants to search/find jobs:
             - Check `Available Resumes` list.
             - IF multiple resumes exist and user didn't pick one -> **CALL `ask_clarification`** with the resume names as `options`.
             - IF only one resume exists -> **CALL `search_jobs`** with that resume.
        
        2. **Apply**:
           - IF user wants to apply to a specific job (e.g. "Apply to @Software Engineer"):
             - IF you have the URL -> **CALL `apply_to_job`** with `job_url`.
             - IF you DO NOT have the URL -> **CALL `apply_to_job`** with `job_title` (extracted from user Request). Do NOT ask for URL. The system will look it up.
        
        3. **General Chat**:
           - If no action is needed, just reply helpful text.
           - If you are unsure, ASK the user.

        **Example Flow**:
        User: "Apply to @Python Dev"
        Assistant: (Calls tool) apply_to_job(job_title="Python Dev", resume_filename="...", mode="cloud")
        """

        # 3. Define Tools
        def search_jobs(resume_filename: str, limit: int = 20, job_title_override: str = "", location_override: str = ""):
            """
            Starts the Researcher Agent to find job leads on ATS sites.
            args:
                resume_filename: The exact filename of the resume to use (must be from Available Resumes list).
                limit: Number of jobs to find (default 20, max 50).
                job_title_override: Specific job title to search for (optional).
                location_override: Specific location (optional).
            """
            return "started_research"

        def apply_to_job(job_url: str = "", job_title: str = "", resume_filename: str = "", mode: str = "cloud", extra_instructions: str = ""):
            """
            Starts the Applier Agent to apply for a job.
            args:
                job_url: The URL of the job post (Optional if title provided).
                job_title: The Title of the job to lookup in DB (Optional if URL provided).
                resume_filename: The exact filename of the resume to use.
                mode: 'cloud' or 'local' (default 'cloud').
                extra_instructions: Any custom instructions for the agent (e.g. 'salary expectation 100k').
            """
            return "started_application"

        def ask_clarification(question: str, options: List[str]):
            """
            Asks the user a clarification question with selectable options.
            args:
                question: The question to ask (e.g. "Which resume?").
                options: List of string options for the user to click.
            """
            return "asked_clarification"

        tools = [search_jobs, apply_to_job, ask_clarification]

        # 4. Format History for Gemini
        contents = []
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
            # Generate with Tools
            # IMPORTANT: Disable automatic function calling so we can intercept the call
            # and return it as an action to the API layer.
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=tools,
                    temperature=0.7,
                    automatic_function_calling={"disable": True}
                )
            )

            print(f"🤖 RAW GEMINI RESPONSE: {response}") # DEBUG LOG

            # Check for Function Calls
            action = None
            response_text = ""

            # Standard text part
            if response.text:
                response_text = response.text

            # Check function calls
            if response.function_calls:
                fc = response.function_calls[0] # Handle first call
                func_name = fc.name
                func_args = dict(fc.args)
                
                if func_name == "search_jobs":
                    action = {
                        "type": "research",
                        "payload": func_args
                    }
                    response_text += f"\n\n🚀 Starting research for **{func_args.get('limit', 20)}** jobs using resume **{func_args.get('resume_filename')}**..."
                
                elif func_name == "apply_to_job":
                    action = {
                        "type": "apply",
                        "payload": func_args
                    }
                    response_text += f"\n\n📝 Starting application for **{func_args.get('job_url')}**..."

                elif func_name == "ask_clarification":
                    action = {
                        "type": "clarification",
                        "payload": func_args
                    }
                    # Text usually comes from model part anyway, but we can append if needed/missing
                    # response_text += f"\n\n{func_args.get('question')}" 
                    pass

            if not response_text and action:
                response_text = "I'm on it."

            return {
                "role": "model",
                "content": response_text,
                "action": action
            }

        except Exception as e:
            print(f"Gemini Chat Error: {e}")
            return {
                "role": "model", 
                "content": "I'm having trouble connecting to my brain right now. Please try again.",
                "action": None
            }
