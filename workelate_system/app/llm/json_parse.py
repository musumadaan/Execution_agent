import json
import re
from typing import Any

def _strip_code_fences(s: str) -> str:
    s = s.strip()
    # remove ```json ... ``` or ``` ... ```
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def extract_json(text: str):
    """
    Extract the first JSON object/array from text and parse it.
    If parsing fails due to trailing garbage, trim after last brace and retry.
    """
    candidate = (text or "").strip()
    if not (candidate.startswith("{") or candidate.startswith("[")):
        start_obj = candidate.find("{")
        start_arr = candidate.find("[")
        start = min([x for x in [start_obj, start_arr] if x != -1], default=-1)
        if start == -1:
            raise ValueError("No JSON object/array found in text")
        candidate = candidate[start:].strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        last_obj = candidate.rfind("}")
        last_arr = candidate.rfind("]")
        last = max(last_obj, last_arr)
        if last != -1:
            candidate2 = candidate[: last + 1]
            return json.loads(candidate2)
        raise
