"""
Orchestrates full task execution.
What it does:
- Loads task and plan
- Runs steps sequentially
- Passes memory between steps
- Updates step status in database
- Handles continuation if task resumes later

And, the main purpose:
Drive planning → execution → completion flow.
"""


from sqlalchemy.ext.asyncio import AsyncSession
from app.agent.executor import run_step
from app.db import crud


async def run_task_until_done(
    db: AsyncSession,
    *,
    user_id: str,
    task_id: str,
):
    outputs = []

    while True:
        step = await crud.get_next_pending_step(db, task_id)

        if not step:
            return {
                "status": "completed",
                "steps_executed": len(outputs),
                "outputs": outputs,
            }

        memory = await crud.load_memory(db, user_id)

        output, _ = await run_step(
            db=db,
            task_id=task_id,
            step_id=step.id,
            step_title=step.title,
            memory=memory,
        )

        await crud.mark_step_done(db, step.id)
        outputs.append({
            "step": step.title,
            "output": output
        })
