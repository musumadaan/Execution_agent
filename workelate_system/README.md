# WorkElate Agent (Groq-only)

Stateful task agent starter:
- Planning (task decomposition)
- Execution (tool calls)
- Memory + preferences (persisted)
- Decision tracing (audit trail)
- Feedback logging

## Setup

python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
# Add GROQ_API_KEY in .env and get the key value from the project docs 
uvicorn app.main:app --reload


link to project docs: https://docs.google.com/document/d/1o3a2U1ZRuZ3l_A41SVZNYjtREN36UpxFmzxippJ27Tw/edit?usp=sharing