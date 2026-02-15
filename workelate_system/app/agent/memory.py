"""
Manages stateful memory for tasks.
What it does:
- Reads stored memory from DB
- Updates memory after step execution
- Provides context to future steps

And, the main purpose:
Allow agent to remember past actions and results.
"""


from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import MemoryKV
from app.db.repo import upsert_memory, get_memory
from app.core.ids import new_id

class MemoryService:
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id

    async def remember_preference(self, key: str, value: str):
        mem = MemoryKV(
            id=new_id("mem"),
            user_id=self.user_id,
            key=key,
            value=value,
            kind="preference",
        )
        await upsert_memory(self.db, mem)

    async def remember_fact(self, key: str, value: str, kind: str = "semantic"):
        mem = MemoryKV(
            id=new_id("mem"),
            user_id=self.user_id,
            key=key,
            value=value,
            kind=kind,
        )
        await upsert_memory(self.db, mem)

    async def snapshot(self) -> dict:
        items = await get_memory(self.db, self.user_id)
        return {f"{m.kind}:{m.key}": m.value for m in items}
