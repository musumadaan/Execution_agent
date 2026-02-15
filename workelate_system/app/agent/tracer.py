"""
Stores detailed execution logs.
What it records:
- LLM decisions
- Tool calls
- Outputs
- Errors
- Reflection evaluations

And, the main purpose:
Observability and debugging of agent behavior.
"""


import json
from app.core.ids import new_id
from app.db.models import TraceEvent
from app.db.repo import add_trace
from sqlalchemy.ext.asyncio import AsyncSession

async def trace(db: AsyncSession, task_id: str, step_id: str, event_type: str, payload: dict):
    tr = TraceEvent(
        id=new_id("tr"),
        task_id=task_id,
        step_id=step_id,
        event_type=event_type,
        payload=json.dumps(payload, ensure_ascii=False),
    )
    await add_trace(db, tr)
