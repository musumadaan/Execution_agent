"""
Runs ONE step of a task safely.
What it does:
- Asks the LLM which tool to use (doc_write or metrics_generate)
- Validates tool name and arguments
- Forces strict schema for doc_write
- Detects bad output (placeholders, domain drift, duplicates)
- If unsafe → creates Clarify document instead of guessing
- Executes tool with retry + self-healing
- Stores traces and reflection


And, the main purpose:
Execute planned steps reliably and safely.
"""


import inspect
import json
import re
from typing import Any, Dict, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.router import llm_json
from app.llm.prompts import EXECUTOR_SYSTEM, ARG_FIXER_SYSTEM
from app.agent.tracer import trace
from app.tools.registry import get_tool


ALLOWED_TOOLS = {"doc_write", "metrics_generate"}
ALLOWED_DOC_TYPES = {
    "prd",
    "gtm",
    "integration_plan",
    "test_plan",
    "checklist",
    "roadmap",
    "kpi_doc",
    "runbook",
    "generic",
    "spec",
    "risk_register",
    "user_research",
    "onboarding",
}


#Safety and logging
def _safe_jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:
        return str(value)


def _pretty(value: Any, limit: int = 4000) -> str:
    try:
        if isinstance(value, (dict, list)):
            s = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            s = str(value)
    except Exception:
        s = repr(value)
    return s[:limit]


def _clarify_title(step_title: str) -> str:
    st = (step_title or "").strip()
    return st if st.lower().startswith("clarify:") else f"Clarify: {st}"


def _normalize_tool_name(tool_name: object) -> str:
    if not isinstance(tool_name, str):
        return "doc_write"
    t = tool_name.strip()
    if "|" in t:
        t = t.split("|")[0].strip()
    if "," in t:
        t = t.split(",")[0].strip()
    if t not in ALLOWED_TOOLS:
        return "doc_write"
    return t


def _clean_args_for_tool(tool, args: object) -> dict:
    if not isinstance(args, dict):
        return {"title": "Output", "content": str(args)}
    try:
        sig = inspect.signature(tool)
        valid_params = set(sig.parameters.keys())
    except Exception:
        valid_params = set()

    if not valid_params:
        return args

    clean = {k: v for k, v in args.items() if k in valid_params}
    dropped = set(args.keys()) - set(clean.keys())
    if dropped:
        print(f"[WARN] Dropping invalid tool args: {dropped}")

    return clean



# Guardrails
_PLACEHOLDER_PATTERNS = [
    r"\[insert[^\]]*\]",
    r"\[target[^\]]*\]",
    r"\[assumption[^\]]*\]",
    r"\[constraint[^\]]*\]",
    r"\[estimated[^\]]*\]",
    r"\btbd\b",
    r"\blorem ipsum\b",
    r"\bbullet\s*1\b",
    r"\bbullet\s*2\b",
    r"\bbullet\s*3\b",
]
def _contains_placeholders(text: str) -> bool:
    low = (text or "").lower()
    for pat in _PLACEHOLDER_PATTERNS:
        if re.search(pat, low, flags=re.IGNORECASE):
            return True
    return False


def _extract_goal_from_context(ctx: Dict[str, Any]) -> str:
    goal = ctx.get("task_goal")
    if isinstance(goal, str):
        return goal.strip()
    return ""

_DRIFT_TOKENS = {
    "e-commerce",
    "ecommerce",
    "crm",
    "law firm",
    "law firms",
    "compliance",
    "hr",
    "ats",
    "resume",
    "logistics",
    "gaming",
    "order management",
    "inventory",
    "billing",
}


def _likely_domain_drift(task_goal: str, step_title: str, content: str) -> bool:
    goal = (task_goal or "").lower()
    out = (content or "").lower()
    if not goal.strip():
        return False
    for tok in _DRIFT_TOKENS:
        if tok in out and tok not in goal:
            return True
    goal_words = {w for w in re.findall(r"[a-z0-9]+", goal) if len(w) >= 4}
    out_words = {w for w in re.findall(r"[a-z0-9]+", out) if len(w) >= 4}

    if not goal_words:
        return True

    overlap = len(goal_words.intersection(out_words))
    if overlap < 2:
        st = (step_title or "").lower()
        st_words = {w for w in re.findall(r"[a-z0-9]+", st) if len(w) >= 4}
        overlap2 = len(goal_words.intersection(st_words.union(out_words)))
        return overlap2 < 2

    return False


def _duplicate_headers(text: str) -> bool:
    lines = (text or "").splitlines()
    headers = [ln.strip() for ln in lines if ln.strip().startswith("## ")]
    seen = set()
    for h in headers:
        if h in seen:
            return True
        seen.add(h)
    return False


def _make_clarify_doc(
    step_title: str,
    task_goal: str,
    assumptions: list[str],
    constraints: list[str],
) -> str:
    goal_line = task_goal.strip() if task_goal.strip() else "(missing)"
    a = assumptions[:6] if assumptions else []
    c = constraints[:6] if constraints else []

    bullets_a = "\n".join([f"- {x}" for x in a]) if a else "- (not provided)"
    bullets_c = "\n".join([f"- {x}" for x in c]) if c else "- (not provided)"

    questions = [
        "What is the exact product category and target user persona for this goal?",
        "What is the #1 pain point we are solving (and top 2 secondary pains)?",
        "What is the primary activation event (what must a user do to get value)?",
        "What is the business model (free, freemium, subscription, enterprise) and expected pricing range?",
        "Any must-have integrations (e.g., Stripe, Apple/Google IAP, wearable devices, analytics stack)?",
        "What is the launch geography and the 6-month success target (users / revenue / retention)?",
    ]
    q_md = "\n".join([f"- {q}" for q in questions])

    return f"""# {_clarify_title(step_title)}

## Context
- **task_goal:** {goal_line}
- **assumptions:**
{bullets_a}
- **constraints:**
{bullets_c}

## Why I’m asking
The previous output risked guessing or drifting from the goal. To keep this step accurate and on-domain, I need the details below.

## Questions
{q_md}
"""


def _ensure_doc_write_args_schema(args: dict) -> dict:
    title = str(args.get("title") or "Document").strip() or "Document"

    content = args.get("content")
    if not isinstance(content, str):
        content = str(content) if content is not None else ""

    doc_type = str(args.get("doc_type") or "generic").strip() or "generic"
    if doc_type not in ALLOWED_DOC_TYPES:
        doc_type = "generic"

    ctx = args.get("context") if isinstance(args.get("context"), dict) else {}
    task_goal = str(ctx.get("task_goal") or "").strip()

    assumptions = ctx.get("assumptions") if isinstance(ctx.get("assumptions"), list) else []
    constraints = ctx.get("constraints") if isinstance(ctx.get("constraints"), list) else []

    # never allow nulls + normalize to string lists
    ctx_fixed = {
        "task_goal": task_goal,
        "assumptions": [str(x) for x in assumptions if str(x).strip()],
        "constraints": [str(x) for x in constraints if str(x).strip()],
    }

    return {
        "title": title,
        "content": content,
        "doc_type": doc_type,
        "context": ctx_fixed,
    }


async def run_step(
    db: AsyncSession,
    *,
    task_id: str,
    step_id: str,
    step_title: str,
    memory: dict,
) -> Tuple[Any, dict]:
    """
    Production-grade step executor with guardrails:
    - strict tool normalization + signature enforcement
    - context required for doc_write
    - placeholder detection
    - domain drift detection
    - if missing context / drift / placeholders -> force Clarify doc_write
    """
    user = f"""Step: {step_title}

Memory snapshot (may include task goal + constraints):
{_pretty(memory, limit=2000)}

Return the tool call JSON.
Choose exactly ONE tool.
"""

    decision = await llm_json(EXECUTOR_SYSTEM, user)
    await trace(db, task_id, step_id, "decision", _safe_jsonable(decision))

    raw_tool_name = decision.get("tool", "doc_write")
    raw_args = decision.get("args", {})

    tool_name = _normalize_tool_name(raw_tool_name)

    await trace(
        db,
        task_id,
        step_id,
        "tool",
        _safe_jsonable({"tool_raw": raw_tool_name, "tool": tool_name, "args": raw_args}),
    )

    # Load tool (fallback safe)
    try:
        tool = get_tool(tool_name)
    except KeyError:
        print(f"[WARN] Unknown tool '{tool_name}', falling back to doc_write")
        tool_name = "doc_write"
        tool = get_tool("doc_write")
        raw_args = {}

    # Enforce doc_write schema *before* execution.
    if tool_name == "doc_write":
        if not isinstance(raw_args, dict):
            raw_args = {}
        raw_args = _ensure_doc_write_args_schema(raw_args)

        # Hard context requirement
        ctx = raw_args["context"]
        task_goal = _extract_goal_from_context(ctx)

        # If task_goal missing, force clarify right away (no guessing)
        if not task_goal:
            ctx_assumptions = ctx.get("assumptions", [])
            ctx_constraints = ctx.get("constraints", [])
            raw_args["title"] = _clarify_title(step_title)
            raw_args["doc_type"] = "generic"
            raw_args["content"] = _make_clarify_doc(
                step_title=step_title,
                task_goal=task_goal,
                assumptions=ctx_assumptions,
                constraints=ctx_constraints,
            )

    # Clean args to match callable signature (also prevents unexpected kwargs)
    clean_args = _clean_args_for_tool(tool, raw_args)

    # Ground metrics_generate to the goal if possible
    if tool_name == "metrics_generate":
        clean_args.setdefault("task_goal", str(memory.get("task_goal", "")).strip())
        clean_args.setdefault("step_title", step_title)

        # If still missing goal, force clarify instead of generic metrics
        if not clean_args.get("task_goal"):
            tool_name = "doc_write"
            tool = get_tool("doc_write")
            raw_args = _ensure_doc_write_args_schema(
                {
                    "title": _clarify_title(step_title),
                    "doc_type": "generic",
                    "content": _make_clarify_doc(step_title, "", [], []),
                    "context": {"task_goal": "", "assumptions": [], "constraints": []},
                }
            )
            clean_args = _clean_args_for_tool(tool, raw_args)

    # Execute with 1 retry (arg fixer)
    output: Any = None
    final_decision = decision

    for attempt in range(2):
        try:
            output = await tool(**clean_args)
            if tool_name == "doc_write":
                out_text = output if isinstance(output, str) else str(output)

                ctx = raw_args.get("context", {}) if isinstance(raw_args, dict) else {}
                task_goal = _extract_goal_from_context(ctx)

                assumptions = ctx.get("assumptions", []) if isinstance(ctx.get("assumptions"), list) else []
                constraints = ctx.get("constraints", []) if isinstance(ctx.get("constraints"), list) else []

                assumptions = [str(x) for x in assumptions if str(x).strip()]
                constraints = [str(x) for x in constraints if str(x).strip()]

                bad_placeholders = _contains_placeholders(out_text)
                bad_dup = _duplicate_headers(out_text)
                bad_drift = _likely_domain_drift(task_goal, step_title, out_text)

                if bad_placeholders or bad_dup or bad_drift:
                    clarify = _make_clarify_doc(step_title, task_goal, assumptions, constraints)

                    output = clarify

                    final_decision = {
                        "tool": "doc_write",
                        "args": {
                            "title": _clarify_title(step_title),
                            "content": clarify,
                            "doc_type": "generic",
                            "context": {
                                "task_goal": task_goal,
                                "assumptions": assumptions,
                                "constraints": constraints,
                            },
                        },
                        "decision": "Forced clarify due to placeholders/duplication/domain drift risk.",
                        "reason": f"bad_placeholders={bad_placeholders}, bad_dup_headers={bad_dup}, bad_domain_drift={bad_drift}",
                        "confidence": 100,
                    }

            break

        except Exception as e:
            print(f"[ERROR] Tool execution failed (attempt {attempt+1}): {e}")

            if attempt == 0:
                try:
                    fix_user = f"""
Tool: {tool_name}

Step title: {step_title}

Original args:
{_pretty(raw_args)}

Error:
{str(e)}

Return ONLY JSON:
{{ "args": {{ ... }} }}
"""
                    fix = await llm_json(ARG_FIXER_SYSTEM, fix_user)
                    fixed_args = fix.get("args", clean_args)

                    # Re-apply doc_write schema enforcement if needed
                    if tool_name == "doc_write" and isinstance(fixed_args, dict):
                        fixed_args = _ensure_doc_write_args_schema(fixed_args)

                    clean_args = _clean_args_for_tool(tool, fixed_args)

                except Exception as heal_err:
                    print(f"[WARN] self-heal failed: {heal_err}")

            if attempt == 1:
                output = {"error": "Tool execution failed after retry", "details": str(e)}

    await trace(db, task_id, step_id, "llm", {"tool_output": _safe_jsonable(output)})

    try:
        reflection_prompt = f"""
Evaluate this step execution.

Step: {step_title}
Output:
{_pretty(output)}

Return ONLY valid JSON:
{{
  "quality_score": 1,
  "success": true,
  "improvement": "..."
}}
"""
        reflection = await llm_json("You evaluate agent performance.", reflection_prompt)
        await trace(db, task_id, step_id, "reflection", _safe_jsonable(reflection))
    except Exception as e:
        print(f"[WARN] reflection failed: {e}")

    return output, final_decision
