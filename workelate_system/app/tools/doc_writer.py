import json
from typing import Any, Dict
from app.tools.registry import register


# --------------------------------------------------
# Rendering helpers
# --------------------------------------------------

def _to_md(value: Any) -> str:
    """Render any value as markdown-safe string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()

    # dict/list → pretty JSON block
    try:
        return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"
    except Exception:
        return str(value)


def _compact_list(xs: Any) -> list[str]:
    """Normalize list-like input into clean string list."""
    if not xs:
        return []
    if isinstance(xs, list):
        return [str(x).strip() for x in xs if str(x).strip()]
    return [str(xs).strip()]


def _no_placeholder(text: str) -> str:
    """Remove obvious template filler tokens."""
    if not text:
        return ""

    lowered = text.lower()

    banned_tokens = [
        "[insert",
        "bullet 1",
        "bullet 2",
        "bullet 3",
        "tbd",
        "lorem ipsum",
    ]

    if any(token in lowered for token in banned_tokens):
        replacements = {
            "[Insert": "",
            "[insert": "",
            "Bullet 1": "",
            "Bullet 2": "",
            "Bullet 3": "",
            "TBD": "",
            "tbd": "",
            "Lorem ipsum": "",
            "lorem ipsum": "",
        }
        for k, v in replacements.items():
            text = text.replace(k, v)

    return text.strip()


def _looks_like_full_doc(md: str) -> bool:
    """
    Detect if markdown already looks like a full structured document.
    Prevents template wrapping twice.
    """
    if not md:
        return False

    md = md.strip()

    if not md.startswith("#"):
        return False

    section_count = md.count("\n## ") + md.count("\n### ")

    strong_section_keywords = [
        "Context",
        "Objective",
        "Requirements",
        "KPIs",
        "Risks",
        "Acceptance",
        "Timeline",
        "Overview",
    ]

    keyword_hits = sum(1 for k in strong_section_keywords if k.lower() in md.lower())

    return section_count >= 2 or keyword_hits >= 3


# --------------------------------------------------
# Main tool
# --------------------------------------------------

@register("doc_write")
async def doc_write(
    title: str,
    content: Any,
    doc_type: str = "generic",
    context: Dict[str, Any] | None = None,
) -> str:
    """
    Domain-neutral structured document generator.

    Behaviour:
    - Converts any content to markdown string
    - If content already looks like a full document → return unchanged
    - Otherwise wraps inside structured template
    - Anchors document to task context
    """

    context = context or {}
    title = (title or "").strip() or "Document"

    task_goal = str(context.get("task_goal", "")).strip()
    assumptions = _compact_list(context.get("assumptions"))
    constraints = _compact_list(context.get("constraints"))
    memory = context.get("memory") or {}

    body = _to_md(content)
    body = _no_placeholder(body)

    # If LLM already generated full structured document → don't wrap again
    if _looks_like_full_doc(body):
        return body

    # --------------------------------------------------
    # Context block
    # --------------------------------------------------

    meta_lines: list[str] = []

    if task_goal:
        meta_lines.append(f"**Task goal:** {task_goal}")

    if assumptions:
        meta_lines.append("**Assumptions:** " + "; ".join(assumptions[:6]))

    if constraints:
        meta_lines.append("**Constraints:** " + "; ".join(constraints[:6]))

    if isinstance(memory, dict) and memory:
        preview = list(memory.keys())[:10]
        meta_lines.append("**Memory keys:** " + ", ".join(preview))

    meta_block = "\n".join(f"- {m}" for m in meta_lines) if meta_lines else "- (not provided)"

    # --------------------------------------------------
    # Templates
    # --------------------------------------------------

    if doc_type == "prd":
        return f"""# {title}

## Context
{meta_block}

## Problem & User
- Who is the user?
- What pain point are we solving?
- What does success look like?

## Requirements
- Must-have
- Should-have
- Nice-to-have

## User Flows
- Happy path
- Edge cases / failure paths

## Non-functional Requirements
- Performance / latency
- Reliability / monitoring
- Security / privacy

## Risks & Mitigations
- Risk: …
  - Mitigation: …

## Acceptance Criteria
- Clear measurable criteria for “done”

## Notes / Inputs
{body}
"""

    if doc_type == "gtm":
        return f"""# {title}

## Context
{meta_block}

## ICP & Positioning
- ICP segments
- Core value proposition
- Differentiators

## Channels & Motion
- Channel 1: …
- Channel 2: …
- Sales motion: self-serve / sales-led / hybrid

## Launch Plan
- Pre-launch
- Launch week
- Post-launch iteration

## KPIs
- North star metric
- Activation metric
- Retention / revenue metric

## Risks & Mitigations
- Risk: …
  - Mitigation: …

## Notes / Inputs
{body}
"""

    if doc_type == "integration_plan":
        return f"""# {title}

## Context
{meta_block}

## Scope
- Systems involved
- Data in/out
- Auth model (API key/OAuth)
- Rate limits + retries

## Data Contract
- Entities
- Required fields
- Versioning strategy

## Failure Handling
- Idempotency
- Retries/backoff
- Dead-letter logging

## Rollout
- Sandbox → pilot → GA

## Acceptance Criteria
- End-to-end sync verified
- Observability in place

## Notes / Inputs
{body}
"""

    if doc_type == "test_plan":
        return f"""# {title}

## Context
{meta_block}

## Test Goals
- What are we validating?

## Test Types
- Unit tests
- Integration tests
- E2E tests
- Load tests (if relevant)

## Test Cases
- Happy paths
- Edge cases
- Error cases

## Success Metrics
- Coverage target
- Performance target
- Reliability target

## Notes / Inputs
{body}
"""

    if doc_type == "checklist":
        return f"""# {title}

## Context
{meta_block}

## Checklist
- [ ] Define owner + due date
- [ ] List deliverables
- [ ] Add acceptance criteria
- [ ] Identify top risks

## Owner / Timeline
- Owner:
- Due date:

## Notes / Inputs
{body}
"""

    # --------------------------------------------------
    # Default template
    # --------------------------------------------------

    return f"""# {title}

## Context
{meta_block}

## Objective
{task_goal or "Define the objective for this document."}

## Key Points
{body}

## Risks & Mitigations
- Risk: …
  - Mitigation: …

## Acceptance Criteria
- Define how we’ll know this is complete and correct

## Next Steps
- Assign an owner
- Set a timeline
- Execute and review outcomes
"""
