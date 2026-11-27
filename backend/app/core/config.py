import os
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Settings:
    app_name: str = "微光数学 · 教研工作台"
    version: str = "V1"
    database_url: str = field(default_factory=lambda: os.environ.get("DATABASE_URL", ""))
    app_origin: str = field(default_factory=lambda: os.environ.get("APP_ORIGIN", "http://localhost:5173").rstrip("/"))
    secure_cookie: bool = field(default_factory=lambda: os.environ.get("COOKIE_SECURE", "true").lower() != "false")
    storage_root: str = field(default_factory=lambda: os.environ.get("STORAGE_ROOT", ""))
    max_file_bytes: int = 200 * 1024 * 1024
    session_seconds: int = 7 * 24 * 3600

settings = Settings()
