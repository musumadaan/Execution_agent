from typing import Callable, Any

TOOLS: dict[str, Callable[..., Any]] = {}

def register(name: str):
    def deco(fn: Callable[..., Any]):
        TOOLS[name] = fn
        return fn
    return deco

def get_tool(name: str):
    if name not in TOOLS:
        raise KeyError(f"Unknown tool: {name}. Known: {list(TOOLS.keys())}")
    return TOOLS[name]
