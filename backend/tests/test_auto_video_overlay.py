"""Test deployment guard logic without starting/stopping any production service."""
import importlib.util
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location("video_overlay_deploy",Path(__file__).resolve().parents[2]/"deploy/auto-video-overlay.py")
deploy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def test_idle_requires_known_terminal_jobs(monkeypatch):
    def fake(path):
        if path=="/jiaoyan/maintenance-state":raise OSError("old adapter")
        return [{"status":"succeeded"},{"status":"cancelled"}]
    monkeypatch.setattr(deploy,"api",fake)
    deploy.ensure_idle()
    def busy(path):
        if path=="/jiaoyan/maintenance-state":raise OSError("old adapter")
        return [{"status":"queued"}]
    monkeypatch.setattr(deploy,"api",busy)
    with pytest.raises(RuntimeError):deploy.ensure_idle()


def test_new_idle_endpoint(monkeypatch):
    monkeypatch.setattr(deploy,"api",lambda path:{"active_jobs":1})
    with pytest.raises(RuntimeError):deploy.ensure_idle()
    monkeypatch.setattr(deploy,"api",lambda path:{"active_jobs":0})
    deploy.ensure_idle()


def test_symlink_rejected(tmp_path):
    target=tmp_path/"target"
    target.write_text("x")
    (tmp_path/"link").symlink_to(target)
    with pytest.raises(RuntimeError):deploy.safe_path(tmp_path,Path("link"))
