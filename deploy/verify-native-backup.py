#!/usr/bin/env python3
"""Offline verification of an encrypted native-state backup.

Decrypt to a private temporary directory, inspect the archive and test the
SQLite mirror. Never modify the worker, live sessions, or business database.
Run on a trusted machine holding the age private identity.
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from pathlib import Path

UUID=re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
OWNER=re.compile(r"[1-9][0-9]{0,9}\Z")
MAX_TOTAL=4*1024**3
MAX_MEMBERS=100000

def allowed(name,is_dir):
    parts=name.split("/")
    if not parts or any(p in ("",".","..") for p in parts):return False
    root=parts[0]
    if root==".jiaoyan-native-workspaces":
        if len(parts)==1:return is_dir
        if not UUID.fullmatch(parts[1]):return False
        if len(parts)==2:return is_dir
        rest=parts[2:]
        if len(rest)==1 and rest[0] in ("owner","sessions.json","session-mirror.sqlite3"):
            return not is_dir
        # Trusted app skill bundle is regenerated on startup. Verify only its known shape.
        if rest[0]==".qoder-cn":
            if len(rest)==1:return is_dir
            if rest[1]!="skills":return False
            if len(rest)==2:return is_dir
            if not re.fullmatch(r"math-[a-z-]+",rest[2]):return False
            if len(rest)==3:return is_dir
            return rest[3:]==["SKILL.md"] and not is_dir
        return False
    if root==".jiaoyan-native-memory":
        if len(parts)==1:return is_dir
        if not OWNER.fullmatch(parts[1]):return False
        if len(parts)==2:return is_dir
        return parts[2:]==["MEMORY.md"] and not is_dir
    return False

def inspect_archive(archive,stage):
    stage=Path(stage)
    seen=set();total=0;mirrors=0;entries=0
    # A stopped worker's backup must not contain WAL or temporary state.
    with tarfile.open(archive,"r:gz") as tar:
        for member in tar:
            name=member.name.rstrip("/")
            if len(seen)>=MAX_MEMBERS or name in seen or not (member.isdir() or member.isfile()) or not allowed(name,member.isdir()):
                raise ValueError("unexpected native backup entry")
            seen.add(name);total+=member.size
            if total>MAX_TOTAL:raise ValueError("native backup exceeds verification size limit")
            dest=stage.joinpath(*name.split("/"))
            if member.isdir():dest.mkdir(parents=True,exist_ok=True,mode=0o700);continue
            dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with tar.extractfile(member) as src, dest.open("xb") as out:
                shutil.copyfileobj(src,out,1024*1024)
            if dest.stat().st_size!=member.size:raise ValueError("incomplete native backup file")
    work=stage/".jiaoyan-native-workspaces"
    if work.exists():
        for directory in work.iterdir():
            owner=(directory/"owner").read_text(encoding="ascii")
            if not OWNER.fullmatch(owner):raise ValueError("invalid workspace owner")
            data=json.loads((directory/"sessions.json").read_text(encoding="utf-8"))
            if not isinstance(data,dict) or any(not isinstance(data.get(k),list) or any(not isinstance(x,str) or not UUID.fullmatch(x) for x in data[k]) for k in ("sessions","jobs")):
                raise ValueError("invalid native session manifest")
            mirror=directory/"session-mirror.sqlite3"
            if mirror.exists():
                db=sqlite3.connect(mirror.as_uri()+"?mode=ro",uri=True)
                try:
                    if db.execute("PRAGMA integrity_check").fetchall()!=[("ok",)]:raise ValueError("SQLite mirror failed integrity check")
                    count=db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
                    entries+=count;mirrors+=1
                finally:db.close()
    if not seen:raise ValueError("empty native backup")
    return {"files_and_dirs":len(seen),"mirrors":mirrors,"transcript_entries":entries,"bytes":total}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--identity",type=Path,required=True)
    args=parser.parse_args()
    os.umask(0o077)
    if not args.archive.is_file() or not args.identity.is_file():raise SystemExit("Archive or age identity not found")
    with tempfile.TemporaryDirectory(prefix="wg-native-verify-") as tmp:
        root=Path(tmp);archive=root/"native.tar.gz"
        subprocess.run(["age","-d","-i",str(args.identity),"-o",str(archive),str(args.archive)],check=True,timeout=900,stdout=subprocess.DEVNULL)
        stage=root/"staged";stage.mkdir(mode=0o700)
        result=inspect_archive(archive,stage)
        print(json.dumps({"status":"ARCHIVE_VERIFIED","live_restore":False,**result}))
if __name__=="__main__":main()
