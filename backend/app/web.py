from pathlib import Path
from fastapi import Request
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

def mount_web(app):
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request):
        from fastapi import HTTPException
        if path == "api" or path.startswith("api/") or path == "assets" or path.startswith("assets/"):
            raise HTTPException(404)
        return FileResponse(dist / "index.html", media_type="text/html")
