"""Protect real worker sockets during the opt-in self-hosted test run."""
import os
import pytest

@pytest.fixture(autouse=True)
def isolate_worker_on_server(monkeypatch, tmp_path):
    if os.environ.get("JIAOYAN_CI_ISOLATION") == "1":
        from app.api import qoder
        monkeypatch.setattr(qoder, "SOCKET", str(tmp_path / "nonexistent-worker.sock"))
