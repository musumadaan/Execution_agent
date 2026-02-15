"""
LLM call wrapper and it does:
- Sends prompts to model provider
- Ensures JSON output
- Handles retries and parsing

Main purpose:
Central interface for all model calls.
"""


import asyncio
import httpx
import json

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.json_parse import extract_json

log = get_logger("llm.router")


class LLMError(RuntimeError):
    pass


def _safe_snippet(text: str, n: int = 400) -> str:
    return (text or "")[:n].replace("\n", "\\n").replace("\r", "\\r")


async def _groq_chat(system: str, user: str) -> str:
    if not settings.GROQ_API_KEY:
        raise LLMError("Missing GROQ_API_KEY. Put it in your .env")

    url = f"{settings.GROQ_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        # IMPORTANT: do NOT force JSON mode; we enforce JSON ourselves via extract_json + repair
    }

    timeout = httpx.Timeout(40.0, connect=10.0)

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, headers=headers, json=payload)

            # Retry transient errors
            if r.status_code in (429, 500, 502, 503, 504):
                msg = f"Groq transient {r.status_code}: {r.text}"
                last_err = LLMError(msg)
                backoff = 0.6 * (2**attempt)
                log.warning(f"{msg}. retrying in {backoff:.1f}s (attempt {attempt+1}/3)")
                await asyncio.sleep(backoff)
                continue

            if r.status_code >= 400:
                raise LLMError(f"Groq error {r.status_code}: {r.text}")

            data = r.json()
            try:
                return data["choices"][0]["message"]["content"]
            except Exception:
                raise LLMError(f"Unexpected Groq response: {data}")

        except Exception as e:
            last_err = e
            backoff = 0.6 * (2**attempt)
            log.warning(f"Groq call failed: {e}. retrying in {backoff:.1f}s (attempt {attempt+1}/3)")
            await asyncio.sleep(backoff)

    raise LLMError(f"Groq call failed after retries: {last_err}")


async def llm_json(system: str, user: str) -> dict:
    """
    Calls Groq and returns a parsed JSON dict.
    Self-repairs if model emits non-JSON / wrong schema.
    Never raises uncaught JSONDecodeError (hard fallback).
    """
    provider = (settings.LLM_PROVIDER or "").lower().strip()

    if provider == "mock":
        return {
            "tool": "doc_write",
            "args": {"title": "Mock Output", "content": user},
            "decision": "Mock tool",
            "reason": "No LLM key",
            "confidence": 50,
        }

    if provider != "groq":
        raise LLMError(f"Unsupported LLM_PROVIDER={settings.LLM_PROVIDER}. Use groq or mock.")

    # ----------------------------
    # Attempt 1
    # ----------------------------
    text = await _groq_chat(system, user)
    try:
        parsed = extract_json(text)
        if not isinstance(parsed, dict):
            raise ValueError(f"JSON is not an object (got {type(parsed).__name__})")
        return parsed
    except Exception as e:
        log.warning(f"JSON parse failed (attempt1): {e}. Snippet={_safe_snippet(text)}. Trying repair...")

    # ----------------------------
    # Attempt 2: strict formatter
    # ----------------------------
    repair_system = "You are a strict JSON formatter. Return ONLY a valid JSON object."
    repair_user = f"Fix and output ONLY a JSON object for this content:\n{text}\nReturn ONLY JSON."
    text2 = await _groq_chat(repair_system, repair_user)

    try:
        parsed2 = extract_json(text2)
        if not isinstance(parsed2, dict):
            raise ValueError(f"Repair JSON is not an object (got {type(parsed2).__name__})")
        return parsed2
    except Exception as e2:
        log.warning(
            f"JSON parse failed (attempt2 repair): {e2}. Snippet={_safe_snippet(text2)}. Trying schema-forced minimal repair..."
        )

    # ----------------------------
    # Attempt 3: schema-forced MINIMAL object (prevents giant broken JSON)
    # ----------------------------
    schema_system = "Return ONLY valid JSON. You MUST match the provided schema exactly."
    schema_user = f"""
You must output a JSON object that matches this schema EXACTLY:

{{
  "tool": "doc_write" | "metrics_generate",
  "args": {{ }},
  "decision": "string",
  "reason": "string",
  "confidence": 0
}}

Rules:
- tool MUST be exactly "doc_write" or "metrics_generate".
- confidence MUST be an integer 0-100.
- Keep args SMALL. Do NOT output long text blocks.
- If tool="doc_write", args MUST be:
  {{
    "title": "string",
    "content": "string"
  }}
  And content MUST be <= 200 characters.
- Return ONLY JSON. Nothing else.

Convert the following into a minimal valid object:

CONTENT:
{text2}
"""
    text3 = await _groq_chat(schema_system, schema_user)

    try:
        parsed3 = extract_json(text3)
        if not isinstance(parsed3, dict):
            raise ValueError(f"Schema repair JSON is not an object (got {type(parsed3).__name__})")
        json.dumps(parsed3)  # ensure serializable
        return parsed3
    except Exception as e3:
        log.error(f"Schema repair parsing failed: {e3}. Snippet={_safe_snippet(text3)}")

        # HARD fallback: never 500
        return {
            "tool": "doc_write",
            "args": {"title": "Step Output", "content": "Fallback: produce a structured document for this step."},
            "decision": "Fallback doc_write",
            "reason": "LLM JSON formatting failed after retries.",
            "confidence": 0,
        }
