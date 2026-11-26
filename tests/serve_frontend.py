"""Serve the exact compiled SPA for CI without reinstalling Node dependencies."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class FrontendHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        path = urlsplit(self.path).path
        if (
            not Path(self.translate_path(path)).exists()
            and "text/html" in self.headers.get("Accept", "")
            and not path.startswith(("/api/", "/assets/"))
            and not Path(path).suffix
        ):
            self.path = "/index.html"
        return super().send_head()


if __name__ == "__main__":
    dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("Missing compiled frontend")
    handler = partial(FrontendHandler, directory=str(dist))
    with ThreadingHTTPServer(("127.0.0.1", 4173), handler) as server:
        server.serve_forever()
