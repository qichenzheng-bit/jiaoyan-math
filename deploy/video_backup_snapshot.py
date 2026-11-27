#!/usr/bin/env python3
"""Capture only durable video business data as the isolated video service account.
The main backup service encrypts each stable file before publishing to its private Git repo.
No provider keys, account sessions, environment files or caches are included.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from datetime import datetime, timezone

TABLES = ("projects", "lessons", "jobs", "edit_records", "edit_session_archives",
          "edit_language_records", "ai_job_runtime", "stored_uploads", "assets", "imported_videos")
ROOTS = ("questions/lessons", "questions/exports", "images/uploads", "images/assets",
         "videos/generated", "videos/imported", "videos/approved")
SETTINGS = ("system:subtitle_style", "system:watermark_style", "system:default_voice")
BASE = Path("/var/lib/jiaoyan-video-backup")

def digest(path):
    with path.open("rb") as f:
        h=hashlib.sha256()
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()

def allowed_path(name):
    p=Path(name)
    return (not p.is_absolute() and ".." not in p.parts and
            any(name.startswith(root+"/") for root in ROOTS))

def files(root):
    for part in ROOTS:
        base=root/part
        if not base.exists():continue
        if base.is_symlink() or not base.resolve().is_relative_to(root):raise ValueError("unsafe video directory")
        for directory, dirs, names in os.walk(base, followlinks=False):
            dirs.sort();names.sort()
            for d in dirs:
                if (Path(directory)/d).is_symlink():raise ValueError("video directory symlink")
            for name in names:
                p=Path(directory)/name
                if not stat.S_ISREG(p.lstat().st_mode):raise ValueError("nonregular video file")
                relative=p.relative_to(root).as_posix()
                if not allowed_path(relative):raise ValueError("unsafe video path")
                yield relative,p

def capture(destination, root, dsn):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    from psycopg import sql
    dsn=dsn.replace("postgresql+psycopg://","postgresql://",1)
    params=conninfo_to_dict(dsn)
    if not params.get("dbname") or params["dbname"] in ("jiaoyan","postgres","template0","template1"):
        raise ValueError("video database must be independent")
    env={k:v for k,v in os.environ.items() if not k.startswith("PG")}
    for k,v in params.items():
        if k in ("host","port","dbname","user","password","sslmode","sslrootcert","sslcert","sslkey","connect_timeout"):
            env["PG"+("DATABASE" if k=="dbname" else k.upper())]=v
    env["PGCONNECT_TIMEOUT"]="10"
    data=destination/"files";data.mkdir()
    index=[]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cur.execute(sql.SQL("LOCK TABLE {} IN SHARE MODE NOWAIT").format(sql.SQL(",").join(sql.Identifier(t) for t in TABLES)))
            cur.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','cancelling')")
            if cur.fetchone()[0]:raise RuntimeError("video jobs active; retry later")
            cur.execute("SELECT pg_export_snapshot()")
            snapshot=cur.fetchone()[0]
            command=["pg_dump","--format=custom","--no-owner","--no-privileges","--snapshot="+snapshot]
            for table in TABLES:command.extend(["--table=public."+table])
            with (destination/"database.dump").open("wb") as out:
                subprocess.run(command,env=env,stdout=out,stderr=subprocess.DEVNULL,check=True,timeout=600)
            cur.execute("SELECT key,value,version FROM client_settings WHERE account_id='' AND key=ANY(%s) ORDER BY key",(list(SETTINGS),))
            (destination/"settings.json").write_text(json.dumps(cur.fetchall(),ensure_ascii=False),encoding="utf-8")
            for relative,source in files(root):
                key=hashlib.sha256(relative.encode()).hexdigest()
                target=data/key
                # O_NOFOLLOW and stat comparison catch replacement and concurrent changes.
                fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
                with os.fdopen(fd,"rb") as inp,target.open("wb") as out:
                    before=os.fstat(inp.fileno())
                    if not stat.S_ISREG(before.st_mode):raise ValueError("invalid video file")
                    h=hashlib.sha256()
                    for block in iter(lambda:inp.read(1024*1024),b""):
                        h.update(block);out.write(block)
                    after=os.fstat(inp.fileno())
                current=source.stat()
                fingerprint=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
                if fingerprint(before)!=fingerprint(after) or fingerprint(after)!=fingerprint(current):
                    raise RuntimeError("video file changed during capture")
                index.append({"path":relative,"key":key,"size":before.st_size,"sha256":h.hexdigest()})
    meta={"format":1,"created_at":datetime.now(timezone.utc).isoformat(),"files":index,
          "database_sha256":digest(destination/"database.dump"),"settings_sha256":digest(destination/"settings.json")}
    (destination/"index.json").write_text(json.dumps(meta,ensure_ascii=False,sort_keys=True),encoding="utf-8")

def main():
    os.umask(0o027)
    root=Path(os.environ["WEIGUANG_STORAGE"]).resolve(strict=True)
    if not root.is_dir() or root==Path("/"):raise ValueError("invalid video storage")
    if BASE.is_symlink() or not BASE.is_dir():raise ValueError("invalid snapshot directory")
    # A separate lock protects readers only during the brief publication switch.
    with (BASE/"capture.lock").open("a") as gate:
        fcntl.flock(gate,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix="next-",dir=BASE) as tmp:
            destination=Path(tmp)/"snapshot";destination.mkdir(mode=0o750)
            capture(destination,root,os.environ["DATABASE_URL"])
            for directory,dirs,names in os.walk(destination):
                Path(directory).chmod(0o2750)
                for name in names:(Path(directory)/name).chmod(0o640)
            with (BASE/"publish.lock").open("a") as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                current=BASE/"current";old=BASE/"previous"
                if old.exists():shutil.rmtree(old)
                if current.exists():current.rename(old)
                destination.rename(current)
            print("Video business snapshot ready")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("Video snapshot failed: "+type(exc).__name__)
        raise SystemExit(1) from None
