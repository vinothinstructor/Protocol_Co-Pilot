from enum import Enum
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMMode(str, Enum):
    MOCK = "mock"      # Template responses, no LLM, no embeddings
    FAKE = "fake"      # Deterministic realistic responses, no Azure
    CACHED = "cached"  # Replay captured real responses
    LIVE = "live"      # Real Azure calls


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://admin:password@localhost:5432/vectordb"

    # LLM mode
    llm_mode: LLMMode = LLMMode.MOCK

    # Azure (only used in live mode)
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_llm_deployment: str = "gpt-4.1-mini"
    azure_embedding_deployment: str = "text-embedding-3-small"

    # Embedding dimension (text-embedding-3-small)
    embedding_dim: int = 1536

    # Server
    backend_port: int = 8002


settings = Settings()
