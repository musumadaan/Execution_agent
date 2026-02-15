"""
Creates the task plan.
What it does:
- Sends the user goal to the LLM planner prompt
- Generates structured steps (JSON plan)
- Ensures steps use valid tools
- Produces assumptions + constraints

And, the main purpose:
Convert a goal into executable steps.
"""



from sqlalchemy.ext.asyncio import AsyncSession
from app.llm.router import llm_json
from app.llm.prompts import PLANNER_SYSTEM
from app.llm.schemas import Plan
from app.agent.tracer import trace

async def make_plan(db: AsyncSession, *, task_id: str, step_id: str, goal: str) -> Plan:
    raw = await llm_json(PLANNER_SYSTEM, goal)
    plan = Plan.model_validate(raw)
    await trace(db, task_id, step_id, "plan", plan.model_dump())
    return plan
