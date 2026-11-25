from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    app_name: str = "微光数学 · 教研工作台"
    version: str = "0.1.0"

settings = Settings()
