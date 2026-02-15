# app/db/repo.py

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Task, TaskStep, MemoryKV, Decision, TraceEvent, Feedback


def _serialize_sqlite_value(value: Any) -> Any:
    """
    SQLite cannot bind dict/list directly into TEXT parameters.
    Convert dict/list to JSON string so commit never fails.

    NOTE:
    - Keep strings as-is.
    - For dict/list, store pretty JSON for readability.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return value


async def create_task(db: AsyncSession, task: Task) -> Task:
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: str) -> Task | None:
    res = await db.execute(select(Task).where(Task.id == task_id))
    return res.scalar_one_or_none()


async def list_steps(db: AsyncSession, task_id: str) -> list[TaskStep]:
    res = await db.execute(
        select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.idx)
    )
    return list(res.scalars().all())


async def add_step(db: AsyncSession, step: TaskStep) -> TaskStep:
    # If result is set during creation, make it SQLite-safe
    if hasattr(step, "result"):
        step.result = _serialize_sqlite_value(getattr(step, "result", None))

    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def update_step(db: AsyncSession, step: TaskStep) -> TaskStep:
    # Ensure step.result is SQLite-safe (dict/list -> JSON string)
    if hasattr(step, "result"):
        step.result = _serialize_sqlite_value(getattr(step, "result", None))

    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def upsert_memory(db: AsyncSession, mem: MemoryKV) -> MemoryKV:
    await db.execute(
        delete(MemoryKV).where(MemoryKV.user_id == mem.user_id, MemoryKV.key == mem.key)
    )
    # If you store non-string values in MemoryKV.value, uncomment this:
    # if hasattr(mem, "value"):
    #     mem.value = _serialize_sqlite_value(getattr(mem, "value", None))

    db.add(mem)
    await db.commit()
    await db.refresh(mem)
    return mem




async def get_memory(db: AsyncSession, user_id: str) -> list[MemoryKV]:
    res = await db.execute(select(MemoryKV).where(MemoryKV.user_id == user_id))
    return list(res.scalars().all())

async def reset_memory(db: AsyncSession, user_id: str) -> None:
    await db.execute(delete(MemoryKV).where(MemoryKV.user_id == user_id))
    await db.commit()


async def add_decision(db: AsyncSession, dec: Decision) -> Decision:
    # Make payload SQLite-safe if it exists and is dict/list
    if hasattr(dec, "payload"):
        dec.payload = _serialize_sqlite_value(getattr(dec, "payload", None))

    db.add(dec)
    await db.commit()
    await db.refresh(dec)
    return dec


async def add_trace(db: AsyncSession, tr: TraceEvent) -> TraceEvent:
    # Make payload SQLite-safe if it exists and is dict/list
    if hasattr(tr, "payload"):
        tr.payload = _serialize_sqlite_value(getattr(tr, "payload", None))

    db.add(tr)
    await db.commit()
    await db.refresh(tr)
    return tr

async def get_trace(db: AsyncSession, task_id: str) -> list[TraceEvent]:
    res = await db.execute(
        select(TraceEvent)
        .where(TraceEvent.task_id == task_id)
        .order_by(TraceEvent.created_at)
    )
    return list(res.scalars().all())


async def add_feedback(db: AsyncSession, fb: Feedback) -> Feedback:
    db.add(fb)
    await db.commit()
    await db.refresh(fb)
    return fb
async def purge_old_decisions(db: AsyncSession) -> None:
    cutoff = datetime.utcnow() - timedelta(days=settings.DECISION_RETENTION_DAYS)
    await db.execute(delete(Decision).where(Decision.created_at < cutoff))
    await db.commit()
