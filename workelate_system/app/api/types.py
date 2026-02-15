"""
API request and response schemas.
What it defines:
- Input payloads
- Response formats
- Validation rules

And, the main purpose:
Ensure structured communication between client and server.
"""


from pydantic import BaseModel, Field

class StartTaskRequest(BaseModel):
    user_id: str = Field(..., description="Your app user identifier")
    goal: str

class FeedbackRequest(BaseModel):
    user_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: str = ""
