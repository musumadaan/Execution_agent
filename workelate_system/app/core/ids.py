import uuid

def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"

"""
ID generation utilities & it provides:
- Unique task IDs
- Step IDs
- Trace IDs

The main purpose:
Consistent identifier creation across system.
"""
