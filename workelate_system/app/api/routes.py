import json
from fastapi import APIRouter, HTTPException
from app.db.session import SessionLocal
from app.db.repo import get_task, list_steps, get_trace, add_feedback, reset_memory
from app.db.models import Feedback
from app.core.ids import new_id
from app.agent.planner import make_plan
from app.agent.executor import run_step
from app.agent.memory import MemoryService
from app.db.models import Task, TaskStep, Decision
from app.db.repo import create_task, add_step, update_step, add_decision
from app.api.types import StartTaskRequest, FeedbackRequest


"""
FastAPI routes for interacting with the agent.
What it provides:
- Create task endpoint
- Run task endpoint
- Fetch task status
- Fetch results

And, the main purpose:
Expose agent functionality over HTTP.
"""

router = APIRouter()
@router.post("/tasks/start")
async def api_start_task(req: StartTaskRequest):
    async with SessionLocal() as db:
        task_id = new_id("task")
        t = Task(id=task_id, user_id=req.user_id, goal=req.goal, status="active")
        await create_task(db, t)

        plan_trace_step_id = new_id("step")
        plan = await make_plan(db, task_id=task_id, step_id=plan_trace_step_id, goal=req.goal)

        for idx, s in enumerate(plan.steps):
            st = TaskStep(id=new_id("step"), task_id=task_id, idx=idx, title=s.title, status="pending")
            await add_step(db, st)

        return {"task_id": task_id, "goal": req.goal, "plan": plan.model_dump()}

@router.post("/tasks/step")
async def api_step(body: dict):
    user_id = body.get("user_id")
    task_id = body.get("task_id")
    if not user_id or not task_id:
        raise HTTPException(400, "user_id and task_id required")

    async with SessionLocal() as db:
        t = await get_task(db, task_id)
        if not t:
            raise HTTPException(404, "task not found")
        if t.user_id != user_id:
            raise HTTPException(403, "user mismatch")

        steps = await list_steps(db, task_id)
        pending = next((s for s in steps if s.status in ("pending", "running")), None)
        if not pending:
            t.status = "done"
            await create_task(db, t)  # harmless upsert-like commit
            return {"task_id": task_id, "status": "done", "message": "No pending steps."}

        pending.status = "running"
        await update_step(db, pending)

        memsvc = MemoryService(db, user_id)
        mem = await memsvc.snapshot()

        output, decision = await run_step(
            db,
            task_id=task_id,
            step_id=pending.id,
            step_title=pending.title,
            memory=mem,
        )

        dec = Decision(
            id=new_id("dec"),
            user_id=user_id,
            task_id=task_id,
            step_id=pending.id,
            decision=str(decision.get("decision", "")),
            reason=str(decision.get("reason", "")),
            confidence=int(decision.get("confidence", 70)),
        )
        await add_decision(db, dec)

        pending.status = "done"
        pending.result = output
        await update_step(db, pending)

        return {"task_id": task_id, "step_id": pending.id, "step_title": pending.title, "output": output}

@router.get("/tasks/{task_id}")
async def api_get_task(task_id: str, user_id: str):
    async with SessionLocal() as db:
        t = await get_task(db, task_id)
        if not t:
            raise HTTPException(404, "task not found")
        if t.user_id != user_id:
            raise HTTPException(403, "user mismatch")

        steps = await list_steps(db, task_id)
        return {
            "task_id": t.id,
            "goal": t.goal,
            "status": t.status,
            "steps": [
                {"id": s.id, "idx": s.idx, "title": s.title, "status": s.status, "result": s.result}
                for s in steps
            ],
        }

@router.get("/tasks/{task_id}/trace")
async def api_trace(task_id: str, user_id: str):
    async with SessionLocal() as db:
        t = await get_task(db, task_id)
        if not t:
            raise HTTPException(404, "task not found")
        if t.user_id != user_id:
            raise HTTPException(403, "user mismatch")
        trace = await get_trace(db, task_id)
        return [
            {
                "id": tr.id,
                "step_id": tr.step_id,
                "type": tr.event_type,
                "payload": json.loads(tr.payload),
                "at": tr.created_at.isoformat(),
            }
            for tr in trace
        ]


@router.post("/tasks/{task_id}/feedback")
async def api_feedback(task_id: str, req: FeedbackRequest):
    async with SessionLocal() as db:
        t = await get_task(db, task_id)
        if not t:
            raise HTTPException(404, "task not found")
        if t.user_id != req.user_id:
            raise HTTPException(403, "user mismatch")
        fb = Feedback(
            id=new_id("fb"),
            task_id=task_id,
            user_id=req.user_id,
            rating=req.rating,
            comment=req.comment,
            applied=False,
        )
        await add_feedback(db, fb)
        return {"ok": True}




@router.post("/memory/reset")
async def api_memory_reset(body: dict):
    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(400, "user_id required")
    async with SessionLocal() as db:
        await reset_memory(db, user_id)
        return {"ok": True}
