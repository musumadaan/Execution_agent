"""
Application configuration loader and it handles:
- Environment variables
- App settings
- Model configuration
- Database configuration

And, the main purpose:
Central place for system configuration.
"""


from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./agent.db"

    # LLM
    LLM_PROVIDER: str = "groq"  # groq | mock (for no-key dev)
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_MODEL: str = "llama-3.3-70b-versatile"

    # Memory governance
    DECISION_RETENTION_DAYS: int = 90
    ALLOW_STORE_RAW_MESSAGES: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
