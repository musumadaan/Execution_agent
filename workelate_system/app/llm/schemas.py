from pydantic import BaseModel, Field
from typing import List, Optional

class PlanStep(BaseModel):
    title: str = Field(..., description="One actionable step")
    tool: Optional[str] = Field(None, description="Preferred tool name")

class Plan(BaseModel):
    goal: str
    assumptions: List[str] = []
    constraints: List[str] = []
    steps: List[PlanStep]
