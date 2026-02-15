from fastapi import FastAPI
from app.api.routes import router
from app.db.session import init_db
import app.tools.doc_writer
import app.tools.metrics


app = FastAPI(title="WorkElate Agent API (Groq-only)", version="0.1.0")
app.include_router(router, prefix="/v1")

@app.on_event("startup")
async def on_startup():
    await init_db()
