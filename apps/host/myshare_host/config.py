from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    model_name: str = "claude-sonnet-5-5"

    # How the host's MCP client reaches the MCP server.
    mcp_transport: Literal["http", "stdio"] = "http"
    mcp_server_url: str = "http://localhost:8001/mcp"
    # stdio mode: the command the host launches (one subprocess per chat request/user).
    mcp_stdio_command: str = "python -m myshare_mcp --transport stdio"
    myshare_api_url: str = "http://localhost:8000"  # passed to the stdio subprocess only

    mcp_debug_wire: bool = False
    host_checkpoint_db: str = "./host_checkpoints.db"
    host_cors_origins: str = "http://localhost:5173"
    max_agent_steps: int = 12
    host_dev_endpoints: bool = True  # /mcp/inspect; turn off in production

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.host_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
