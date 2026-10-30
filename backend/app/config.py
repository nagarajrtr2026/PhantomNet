from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PHANTOMNET_",
        env_file=".env",
        extra="ignore",
    )

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = ["http://localhost:3000"]
    event_history_size: int = Field(default=1000, ge=10, le=10000)
    max_websocket_clients: int = Field(default=100, ge=1, le=1000)
    max_sessions: int = Field(default=5000, ge=1, le=100000)
    chroma_persist_directory: str = "./.phantomnet/chroma"
    chroma_collection: str = "phantomnet_context"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1"
    max_input_bytes: int = Field(default=16384, ge=256, le=1048576)
    max_file_bytes: int = Field(default=1048576, ge=1, le=16777216)
    network_capture_enabled: bool = False
    fuse_mountpoint: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
