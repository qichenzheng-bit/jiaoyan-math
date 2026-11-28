#!/usr/bin/env python3
"""Non-root, narrowly authorized update of the installed video code only.

Invoked with the main application stopped. Never edits the unit, dependencies,
worker, account credentials, DB, storage, or root-managed directories. Refuse
unknown layouts, busy queues, symlinks and failed prechecks. Roll back on failure.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, build_opener, ProxyHandler

RUNTIME = Path("/opt/jiaoyan-video/runtime-fec8a4f")
PYTHON = Path("/opt/jiaoyan-video/venv/bin/python")
REVISION = "fec8a4f8c21b829a8f043a2c3538aff4cc48ea08"
SERVICE = "jiaoyan-video.service"
PREFIXES = ("app/backend/src/", "app/animation_engine/src/")
FINAL_STATES = {"succeeded", "success", "completed", "done", "failed", "cancelled", "canceled", "interrupted"}
OPENER = build_opener(ProxyHandler({}))


def command(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def service(action):
    command("sudo", "-n", "/usr/bin/systemctl", action, SERVICE, timeout=90)


def api(path):
    port = os.environ.get("VIDEO_ENGINE_PORT", "8766")
    token = os.environ.get("VIDEO_ENGINE_TOKEN", "")
    if port != "8766" or not token:
        raise RuntimeError("Video engine configuration unavailable")
    req = Request("http://127.0.0.1:" + port + "/api/v1" + path, headers={"X-API-Key":token})
    with OPENER.open(req, timeout=5) as response:
        return json.loads(response.read(8 * 1024 * 1024))


def health():
    for _ in range(20):
        try:
            if isinstance(api("/lessons/stats"), dict):
                return
        except Exception:
            time.sleep(1)
    raise RuntimeError("Video engine health check failed")


def ensure_idle():
    # On the old adapter the full job listing is the only read-only interface.
    # If it fills the page, completeness is unknown: defer rather than interrupt.
    try:
        state = api("/jiaoyan/maintenance-state")
    except Exception:
        jobs = api("/jobs?limit=200")
        if not isinstance(jobs, list) or len(jobs) >= 200:
            raise RuntimeError("Cannot establish complete idle job listing")
        if any(not isinstance(job, dict) or job.get("status") not in FINAL_STATES for job in jobs):
            raise RuntimeError("Video engine has active or unknown jobs")
    else:
        if not isinstance(state, dict) or state.get("active_jobs") != 0:
            raise RuntimeError("Video engine has active or unknown jobs")


def safe_path(root, relative, *, existing=False):
    p = root / relative
    if p == root or not p.is_relative_to(root):
        raise RuntimeError("Invalid overlay path")
    cursor = root
    for part in relative.parts:
        if part in {"..", ".", ""}:
            raise RuntimeError("Invalid overlay component")
        cursor /= part
        if cursor.is_symlink():
            raise RuntimeError("Unexpected overlay symlink")
    if p.exists():
        info = p.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError("Unexpected overlay target")
    elif existing:
        raise RuntimeError("Missing staged source")
    return p


def collect(release):
    overlay = release / "vendor/video-overlay"
    files = {}
    for source in sorted(overlay.rglob("*")):
        if source.is_symlink():
            raise RuntimeError("Unexpected staged symlink")
        if not source.is_file():
            continue
        relative = source.relative_to(overlay)
        if not relative.as_posix().startswith(PREFIXES):
            raise RuntimeError("Invalid overlay scope")
        files[relative] = safe_path(overlay, relative, existing=True)
    files[Path("video_qoder_adapter.py")] = safe_path(release, Path("deploy/video_qoder_adapter.py"), existing=True)
    return files


def digest(path):
    return hashlib.sha256(path.read_bytes()).digest()


def run(release):
    if pwd.getpwuid(os.getuid()).pw_name != "jiaoyan" or os.getuid() == 0:
        raise RuntimeError("Requires non-root deployment account")
    if not RUNTIME.exists():
        print("VIDEO_OVERLAY_NOT_INSTALLED")
        return
    if RUNTIME.is_symlink() or RUNTIME.resolve() != RUNTIME or (RUNTIME / "SOURCE_REVISION").read_text().strip() != REVISION:
        raise RuntimeError("Unexpected video runtime layout")
    files = collect(release)
    changed = {rel:src for rel,src in files.items() if not safe_path(RUNTIME,rel).exists() or digest(RUNTIME/rel)!=digest(src)}
    if not changed:
        print("VIDEO_OVERLAY_ALREADY_CURRENT")
        return
    props = subprocess.check_output(["systemctl","show",SERVICE,"--property=User,Group,ExecStartPre,ExecStartPost,ExecStop,ExecStopPost,ExecCondition,WorkingDirectory,ExecStart"], text=True)
    info = dict(line.split("=",1) for line in props.splitlines() if "=" in line)
    if info.get("User")!="jiaoyan-video" or info.get("Group")!="jiaoyan-video" or any(info.get(k) for k in ("ExecStartPre","ExecStartPost","ExecStop","ExecStopPost","ExecCondition")):
        raise RuntimeError("Unexpected privileged service hooks or account")
    if info.get("WorkingDirectory")!=str(RUNTIME) or "video_qoder_adapter:create_app" not in info.get("ExecStart",""):
        raise RuntimeError("Unexpected video service entry point")
    for rel in changed:
        target = RUNTIME / rel
        parent = target.parent
        while not parent.exists():
            parent = parent.parent
        if not os.access(target if target.exists() else parent, os.W_OK):
            raise RuntimeError("Missing narrow overlay write permission: " + str(rel))
    # Verify the actual candidate against installed runtime dependencies, no AI.
    staged = release / "video-engine-source"
    env = {**os.environ, "PYTHONPATH":str(staged/"app/backend/src")+":"+str(staged/"app/animation_engine/src"), "PYTHONDONTWRITEBYTECODE":"1"}
    env.pop("VIDEO_ENGINE_TOKEN", None)
    command(str(PYTHON), str(release/"deploy/video-engine-overlay-check.py"), env=env, timeout=120)
    ensure_idle()
    with tempfile.TemporaryDirectory(prefix="video-overlay-rollback-") as tmp:
        backup = Path(tmp)
        existed = {}
        for rel in changed:
            dst = RUNTIME / rel
            existed[rel] = dst.exists()
            if existed[rel]:
                (backup/rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dst, backup/rel)
        # Stop only the explicitly granted service, never the shared Qoder worker.
        service("stop")
        try:
            for rel, source in changed.items():
                dst = safe_path(RUNTIME, rel)
                dst.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                if dst.exists():
                    dst.write_bytes(source.read_bytes())
                else:
                    with dst.open("xb") as handle:
                        handle.write(source.read_bytes())
                    dst.chmod(0o644)
            service("start")
            health()
            capability = api("/jiaoyan/prompt-capability")
            if capability.get("knowledge_video_schema") != "knowledge-video-source-v1":
                raise RuntimeError("Updated video capability missing")
        except BaseException:
            service("stop")
            for rel, present in existed.items():
                dst = safe_path(RUNTIME, rel)
                if present:
                    dst.write_bytes((backup/rel).read_bytes())
                else:
                    dst.unlink(missing_ok=True)
            service("start")
            health()
            print("VIDEO_OVERLAY_ROLLED_BACK", file=sys.stderr)
            raise
    print("VIDEO_OVERLAY_AUTO_UPGRADED", len(changed))


if __name__ == "__main__":
    try:
        run(Path(sys.argv[1]).resolve())
    except Exception as exc:
        print("VIDEO_OVERLAY_DEFERRED_OR_FAILED:", str(exc), file=sys.stderr)
        raise SystemExit(1)
