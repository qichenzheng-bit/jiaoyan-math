#!/usr/bin/env python3
"""Export only app-owned native mirrors, encrypted before leaving the Worker UID.
A per-workspace online snapshot, not a cross-database point-in-time restore.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

UUID=re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
OWNER=re.compile(r"[1-9][0-9]{0,9}\Z")
SMOKE_OWNER="2147483647"
MAX_BYTES=4*1024**3

def regular(path,limit):
    flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
    fd=os.open(path,flags)
    with os.fdopen(fd,"rb") as f:
        info=os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:
            raise ValueError("unexpected native file")
        raw=f.read(limit+1)
        if len(raw)>limit:raise ValueError("native file too large")
        return raw

def directory(path):
    return path.is_dir() and not path.is_symlink()

def manifest(raw):
    data=json.loads(raw)
    if not isinstance(data,dict) or any(not isinstance(data.get(k),list) or any(not isinstance(x,str) or not UUID.fullmatch(x) for x in data[k]) for k in ("sessions","jobs")):
        raise ValueError("invalid native manifest")

def collect(home,stage):
    work=home/".jiaoyan-native-workspaces"
    mem=home/".jiaoyan-native-memory"
    total=0
    for source in (work,mem):
        if not source.exists():continue
        if not directory(source):raise ValueError("unexpected native root")
        (stage/source.name).mkdir(mode=0o700)
        for p in sorted(source.iterdir()):
            if not directory(p):raise ValueError("unexpected native directory")
            if source==work:
                if not UUID.fullmatch(p.name):raise ValueError("invalid workspace ID")
                owner=regular(p/"owner",32).decode("ascii")
                if not OWNER.fullmatch(owner):raise ValueError("invalid native owner")
                if owner==SMOKE_OWNER:continue
                before=regular(p/"sessions.json",500000);manifest(before)
                target=stage/source.name/p.name;target.mkdir(mode=0o700)
                dbpath=p/"session-mirror.sqlite3"
                if dbpath.exists():
                    if dbpath.is_symlink() or not dbpath.is_file() or dbpath.stat().st_nlink!=1 or dbpath.stat().st_size>MAX_BYTES-total:raise ValueError("invalid native mirror")
                    src=sqlite3.connect(dbpath.as_uri()+"?mode=ro",uri=True,timeout=5)
                    dst=sqlite3.connect(target/"session-mirror.sqlite3")
                    try:
                        src.backup(dst,pages=128,sleep=.05)
                        if dst.execute("PRAGMA quick_check").fetchall()!=[("ok",)]:raise ValueError("native mirror integrity error")
                        dst.execute("SELECT COUNT(*) FROM entries").fetchone()
                    finally:dst.close();src.close()
                    total+=(target/"session-mirror.sqlite3").stat().st_size
                # Reject concurrent workspace deletion or session registration rather
                # than publish an inconsistent manifest. Next timer retries.
                if before!=regular(p/"sessions.json",500000) or owner!=regular(p/"owner",32).decode("ascii"):
                    raise ValueError("native workspace changed during capture")
                (target/"owner").write_text(owner,encoding="ascii")
                (target/"sessions.json").write_bytes(before)
                total+=len(before)+len(owner)
            else:
                if not OWNER.fullmatch(p.name):raise ValueError("invalid memory owner")
                if p.name==SMOKE_OWNER:continue
                memory=p/"MEMORY.md"
                if not memory.exists():continue
                raw=regular(memory,1024*1024)
                if raw!=regular(memory,1024*1024):raise ValueError("native memory changed during capture")
                target=stage/source.name/p.name;target.mkdir(mode=0o700)
                (target/"MEMORY.md").write_bytes(raw);total+=len(raw)
            if total>MAX_BYTES:raise ValueError("native snapshot too large")
    # Include empty roots, so a later empty snapshot does not resurrect deleted chats.
    for name in (work.name,mem.name):
        (stage/name).mkdir(mode=0o700,exist_ok=True)
    return total

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--home",type=Path,required=True)
    parser.add_argument("--recipient",required=True)
    args=parser.parse_args()
    if os.geteuid()==0 or args.home!=Path.home() or not re.fullmatch(r"age1[0-9a-z]{20,100}",args.recipient):raise SystemExit("Invalid snapshot execution context")
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="wg-native-capture-") as tmp:
        root=Path(tmp);stage=root/"stage";stage.mkdir(mode=0o700)
        collect(args.home,stage)
        archive=root/"mirror.tar.gz"
        with tarfile.open(archive,"w:gz") as tar:
            for path in sorted(stage.iterdir()):tar.add(path,arcname=path.name)
        subprocess.run(["age","-r",args.recipient,str(archive)],stdout=sys.stdout.buffer,check=True,timeout=300)
if __name__=="__main__":main()
