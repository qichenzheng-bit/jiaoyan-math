#!/usr/bin/env python3
"""Encrypted, incremental Git snapshots of the local PostgreSQL teaching database.
Run as the existing jiaoyan account. No production restore or credential export.
"""
import argparse
import csv
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

REMOTE = "git@github.com:qichenzheng-bit/jiaoyan-data.git"
BASE = Path.home() / "jiaoyan-app"
STATE = BASE / "backup-state"
CONFIG = BASE / "config" / "backup.json"
CHUNK = 32 * 1024 * 1024
# Must agree with app.services.storage.PURGE_LOCK.
PURGE_LOCK = 824650219
MANIFEST = "manifests/latest.json"
SAFE_SETTINGS = ("display_name", "theme", "ai.qoder.model", "ai.qoder.video_model",
                 "ai.qoder.effort", "ai.qoder.video_effort", "qiandao.qoder_cn.v1", "knowledge.library.directories.v1")
# Logical directory, table, fixed SQL predicate, deterministic ordering.
EXPORTS = [
    ("database/alembic_version", "alembic_version", "true", "version_num"),
    ("teaching/questions/questions", "teaching_resources", "kind='question'", "id"),
    ("teaching/knowledge/units", "teaching_resources", "kind='knowledge'", "id"),
    ("teaching/sources/sources", "teaching_resources", "kind='source'", "id"),
    ("teaching/sources/catalog_details", "source_catalog_details", "true", "source_id"),
    ("teaching/sources/links", "resource_source_links", "true", "resource_id,source_id,provenance_role"),
    ("system/versions/resource_versions", "resource_source_versions", "true", "source_id,version"),
    ("teaching/graph/points", "knowledge_point_catalog", "true", "id"),
    ("teaching/graph/resource_links", "resource_knowledge_links", "true", "resource_id,knowledge_id,role"),
    ("teaching/graph/aliases", "knowledge_aliases", "true", "knowledge_id,normalized"),
    ("teaching/graph/relations", "knowledge_relations", "true", "source_id,target_id,relation_type"),
    ("teaching/intake/documents", "teaching_documents", "kind='intake'", "id"),
    ("production/papers/documents", "teaching_documents", "kind='paper'", "id"),
    ("production/handouts/documents", "teaching_documents", "kind='handout'", "id"),
    ("production/textbooks/documents", "teaching_documents", "kind='textbook'", "id"),
    ("production/documents/versions", "teaching_document_versions", "true", "document_id,revision"),
    ("teaching/documents/references", "document_resource_refs", "true", "document_id,resource_id"),
    ("teaching/intake/registrations", "document_registrations", "true", "id"),
    ("teaching/intake/imports", "intake_imports", "true", "id"),
    ("teaching/intake/jobs", "intake_jobs", "true", "id"),
    ("teaching/intake/supplements", "intake_supplements", "true", "id"),
    ("ai/work/sessions", "work_sessions", "true", "id"),
    ("ai/work/materials", "work_materials", "true", "id"),
    ("ai/work/batches", "work_batches", "true", "id"),
    ("ai/tasks/document_edits", "document_ai_edits", "true", "id"),
    ("ai/chats/sessions", "chat_sessions", "true", "id"),
    ("ai/chats/messages", "chat_messages", "true", "id"),
    ("production/covers/assets", "studio_items", "kind='asset'", "id"),
    ("production/works/works", "studio_items", "kind='work'", "id"),
    ("production/finished/works", "teaching_works", "true", "id"),
    ("production/finished/versions", "teaching_work_versions", "true", "work_id,number"),
    ("production/finished/assets", "teaching_work_assets", "true", "work_id,version,role"),
    ("production/finished/pending_covers", "teaching_work_pending_covers", "true", "work_id"),
    ("operations/publishing/publications", "studio_items", "kind='publication'", "id"),
    ("system/checkin/accounts", "studio_items", "kind='account'", "id"),
    ("system/checkin/history", "studio_items", "kind='checkin'", "id"),
    ("system/versions/studio_versions", "studio_revisions", "true", "item_id,revision"),
    ("production/videos/projects", "video_projects", "true", "id"),
    ("files/metadata", "files", "true", "id"),
    ("files/references", "file_references", "true", "file_id,owner_type,owner_id"),
]
EXCLUDED = {"users", "sessions"}
TABLES = {e[1] for e in EXPORTS} | EXCLUDED | {"settings", "audit_logs"}
SCHEMAS = ["database/schema-pre.sql", "database/schema-post.sql"]
FIXED = {p + ".csv": t for p, t, _, _ in EXPORTS}
FIXED.update({"system/settings/preferences.csv": "settings", "system/checkin/state.csv": "settings",
              "system/versions/audit.csv": "audit_logs"})
FILE_KEY = re.compile(r"(original|generated)/([0-9a-f-]{36})\Z")


def business_settings(cur):
    cur.execute("SELECT key,value FROM public.settings WHERE key = ANY(%s) OR key ~ '^bank[.]history[.][0-9a-f-]{36}[.][0-9a-f-]{36}$' OR key ~ '^bank[.]cart[.][0-9]+$' OR key ~ '^source[.]statistics[.]scopes[.][0-9]+$' OR key ~ '^knowledge[.]unit[.]detail[.][0-9a-f-]{36}$' OR key ~ '^source[.]file[.]versions[.][0-9a-f-]{36}$' OR key ~ '^layout:[0-9]+:[0-9a-f]{64}$' OR key ~ '^ai[.]memory[.][0-9]+[.]all$' OR key ~ '^ai[.]prompt[.][0-9]+[.](global|chat|work|intake|document|video|cover)$' ORDER BY key", (list(SAFE_SETTINGS),))
    result=dict(cur.fetchall())
    # Preserve only completed native chat anchors, not active prompts or tool payloads.
    cur.execute("""SELECT s.key,s.value,m.session_id FROM public.settings s
        JOIN public.chat_messages m ON s.key='ai.chat.active.' || CAST(m.id AS text)
        WHERE m.role='assistant' AND m.state='done' ORDER BY s.key""")
    for key,value,workspace in cur.fetchall():
        anchor=native_chat_anchor(value,str(workspace))
        if anchor is not None:result[key]=anchor
    return result

def native_chat_anchor(raw,workspace):
    try:data=json.loads(raw)
    except (ValueError,TypeError):return None
    if not isinstance(data,dict) or data.get("native") is not True or data.get("phase")!="terminal" or data.get("workspace")!=workspace:return None
    uid=data.get("native_actor")
    if type(uid) is not int or not 0<uid<2147483647:return None
    uuid_pattern=r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
    if any(not isinstance(data.get(k),str) or not re.fullmatch(uuid_pattern,data[k]) for k in ("workspace","native_session","job")):return None
    return json.dumps({k:data[k] for k in ("native","phase","native_actor","workspace","native_session","job")},ensure_ascii=False)

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def safe_path(root, name):
    p = root / name
    if Path(name).is_absolute() or ".." in Path(name).parts or not p.resolve().is_relative_to(root.resolve()):
        raise ValueError("unsafe path")
    for parent in (p, *p.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("symlink not allowed")
    return p


def run(args, *, cwd=None, env=None, output=None):
    result = subprocess.run(args, cwd=cwd, env=env, stdout=output or subprocess.PIPE,
                            stderr=subprocess.DEVNULL, check=False, timeout=900)
    if result.returncode:
        raise RuntimeError("command failed: " + Path(args[0]).name)
    return result.stdout


def db_env():
    # Deployment uses local peer auth; reject configuration drift instead of exporting a different DB.
    if os.environ.get("DATABASE_URL") != "postgresql+psycopg:///jiaoyan":
        raise ValueError("unsupported database configuration")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env.update(PGHOST="/var/run/postgresql", PGDATABASE="jiaoyan", PGUSER="jiaoyan",
               PGCONNECT_TIMEOUT="10")
    return env


def write_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def read_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def now():
    return datetime.now(timezone.utc).isoformat()


def config():
    if CONFIG.is_symlink() or CONFIG.stat().st_mode & 0o077:
        raise ValueError("backup config must be private")
    c = read_json(CONFIG)
    if not re.fullmatch(r"age1[0-9a-z]{20,100}", c.get("recipient", "")):
        raise ValueError("invalid age recipient")
    key = Path(c["ssh_key"]).expanduser()
    hosts = Path(c["known_hosts"]).expanduser()
    if not key.is_file() or key.stat().st_mode & 0o077 or not hosts.is_file():
        raise ValueError("SSH configuration unavailable")
    return c["recipient"], key.resolve(), hosts.resolve()


def git_env(key, hosts):
    env = {k:v for k,v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null",
               GIT_SSH_COMMAND=shlex.join(["ssh", "-i", str(key), "-o", "IdentitiesOnly=yes",
                 "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                 "-o", "UserKnownHostsFile=" + str(hosts), "-o", "ConnectTimeout=15"]))
    return env


def logical_allowed(name):
    return (name in FIXED or name in SCHEMAS or
            re.fullmatch(r"files/(originals|assets)/[0-9a-f-]{36}", name) is not None or
            re.fullmatch(r"production/video-engine/(index\.json|database\.dump|settings\.json|files/[0-9a-f]{64})",name) is not None or
            name == NATIVE_ARCHIVE)


WORK_EXPORTS={"ai/work/sessions.csv","ai/work/materials.csv","ai/work/batches.csv"}
CATALOG_EXPORTS={"teaching/sources/catalog_details.csv"}
DOCUMENT_VERSION_EXPORTS={"production/documents/versions.csv"}
FINISHED_WORK_EXPORTS={name+".csv" for name,table,_,_ in EXPORTS if name.startswith("production/finished/")}

def check_manifest(repo, manifest, allow_legacy=False):
    if manifest.get("format") != 2 or not isinstance(manifest.get("entries"), dict):
        raise ValueError("invalid manifest")
    for name, entry in manifest["entries"].items():
        if not logical_allowed(name) or not entry.get("parts"):
            raise ValueError("invalid manifest entry")
        for index, part in enumerate(entry["parts"]):
            expected = name + ".age." + str(index).zfill(4)
            if part.get("path") != expected or digest(safe_path(repo, expected)) != part.get("sha256"):
                raise ValueError("ciphertext verification failed")
    video={n for n in manifest["entries"] if n.startswith("production/video-engine/")}
    if video and not {"production/video-engine/"+n for n in ("index.json","database.dump","settings.json")}<=video:
        raise ValueError("incomplete video snapshot")
    missing=(set(FIXED) | set(SCHEMAS))-set(manifest["entries"])
    legacy_groups=(WORK_EXPORTS,CATALOG_EXPORTS,DOCUMENT_VERSION_EXPORTS,FINISHED_WORK_EXPORTS)
    allowed_missing={frozenset().union(*(group for i,group in enumerate(legacy_groups) if mask&(1<<i))) for mask in range(1,1<<len(legacy_groups))}
    if missing and not (allow_legacy and frozenset(missing) in allowed_missing):
        raise ValueError("incomplete database backup")


def sanitize_checkin(value):
    # Current provider stores PAT separately; never restore automatic claiming or raw provider payloads.
    source = json.loads(value)
    if not isinstance(source, dict):
        raise ValueError("invalid check-in state")
    def fields(obj, keys):
        return {k: obj[k] for k in keys if k in obj} if isinstance(obj, dict) else {}
    def record(obj):
        return fields(obj, ("round", "state", "earned", "at", "attempts", "mode"))
    def quota(obj):
        q = fields(obj, ("balance", "at", "source"))
        if isinstance(obj, dict):
            q["packs"] = [fields(p, ("kind", "label", "remaining", "total", "used")) for p in obj.get("packs", [])]
        return q
    def history(obj):
        out = {"history": [record(r) for r in obj.get("history", [])],
               "changes": [fields(r, ("at", "from_at", "delta", "balance")) for r in obj.get("changes", [])]}
        if isinstance(obj.get("last"), dict):
            out["last"] = record(obj["last"])
        if isinstance(obj.get("quota"), dict):
            out["quota"] = quota(obj["quota"])
        if isinstance(obj.get("daily"), dict):
            out["daily"] = fields(obj["daily"], ("day", "increase", "decrease", "intervals"))
        return out
    result = history(source)
    result["enabled"] = False
    result["archives"] = [history(a) for a in source.get("archives", []) if isinstance(a, dict)]
    return json.dumps(result, ensure_ascii=False, sort_keys=True)


def copy_out(cur, query, dest):
    with dest.open("wb") as f, cur.copy("COPY (" + query + ") TO STDOUT WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')") as cp:
        for data in cp:
            f.write(data)


def capture(work, publish):
    import psycopg
    env = db_env()
    source = Path(os.environ["STORAGE_ROOT"])
    if not source.is_absolute() or not source.is_dir():
        raise ValueError("storage unavailable")
    source = source.resolve()
    # Acquire the shared lock on a separate autocommit connection BEFORE creating the repeatable-read snapshot.
    with psycopg.connect("host=/var/run/postgresql dbname=jiaoyan user=jiaoyan connect_timeout=10",autocommit=True) as gate:
        gate.execute("SELECT pg_advisory_lock_shared(%s)",(PURGE_LOCK,))
        with psycopg.connect("host=/var/run/postgresql dbname=jiaoyan user=jiaoyan connect_timeout=10") as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                if {r[0] for r in cur.fetchall()} != TABLES:
                    raise ValueError("schema table inventory changed; review backup mapping")
                for table, allowed in (("teaching_resources", ("question","knowledge","source")),
                                       ("teaching_documents", ("intake","paper","handout","textbook")),
                                       ("studio_items", ("asset","work","publication","account","checkin"))):
                    cur.execute("SELECT DISTINCT kind FROM public." + table)
                    if not {r[0] for r in cur.fetchall()}.issubset(allowed):
                        raise ValueError("unknown business kind")
                cur.execute("SELECT pg_export_snapshot()")
                snapshot = cur.fetchone()[0]
                tmp = work / "plain"
                for section, name in zip(("pre-data", "post-data"), SCHEMAS):
                    with tmp.open("wb") as f:
                        run(["pg_dump", "--schema-only", "--no-owner", "--no-privileges",
                             "--section=" + section, "--snapshot=" + snapshot], env=env, output=f)
                    # Recent pg_dump emits random paired psql restrict keys; ignore them only for change detection.
                    h = hashlib.sha256()
                    with tmp.open("rb") as f:
                        for line in f:
                            if not line.startswith((b"\\restrict ", b"\\unrestrict ")):
                                h.update(line)
                    publish(name, tmp, h.hexdigest())
                for path, table, predicate, order in EXPORTS:
                    copy_out(cur, "SELECT * FROM public." + table + " WHERE " + predicate + " ORDER BY " + order, tmp)
                    publish(path + ".csv", tmp)
                settings = business_settings(cur)
                for name, rows in (
                    ("system/settings/preferences.csv", [(k,v) for k,v in settings.items() if k != "qiandao.qoder_cn.v1"]),
                    ("system/checkin/state.csv", [("qiandao.qoder_cn.v1", sanitize_checkin(settings["qiandao.qoder_cn.v1"]))] if "qiandao.qoder_cn.v1" in settings else []),
                ):
                    with tmp.open("w", encoding="utf-8", newline="") as f:
                        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                        writer.writerow(["key", "value"])
                        writer.writerows(rows)
                    publish(name, tmp)
                copy_out(cur, "SELECT id,action,NULL::integer AS user_id,created_at FROM public.audit_logs ORDER BY id", tmp)
                publish("system/versions/audit.csv", tmp)
                cur.execute("SELECT storage_key,sha256,size_bytes FROM public.files WHERE to_jsonb(files)->>'purged_at' IS NULL ORDER BY id")
                for key, sha, size in cur.fetchall():
                    match = FILE_KEY.fullmatch(key)
                    if not match:
                        raise ValueError("invalid storage key")
                    path = safe_path(source, key)
                    # Stored files are immutable after registration. Never include unregistered or staging files.
                    if not path.is_file() or path.stat().st_size != size or digest(path) != sha:
                        raise ValueError("registered attachment missing or corrupted")
                    name = "files/" + ("originals" if match[1] == "original" else "assets") + "/" + match[2]
                    publish(name, path, sha)
                tmp.unlink(missing_ok=True)


VIDEO_PREFIX="production/video-engine/"
VIDEO_BASE=Path("/var/lib/jiaoyan-video-backup")
NATIVE_BASE=Path("/var/lib/jiaoyan-native-backup")
NATIVE_ARCHIVE="ai/native-state/mirror.tar.gz.age"

def native_capture(work,recipient):
    """Copy only an already-encrypted, atomically published root-owned archive."""
    source=NATIVE_BASE/"current.age"
    meta=NATIVE_BASE/"recipient"
    if not source.is_file() or not meta.is_file():return None
    if source.is_symlink() or meta.is_symlink() or NATIVE_BASE.is_symlink():raise ValueError("unsafe native backup path")
    if meta.read_text(encoding="ascii").strip()!=recipient:return None
    dest=work/"native-mirror.age"
    with source.open("rb") as src:
        stat=os.fstat(src.fileno())
        age_seconds=datetime.now(timezone.utc).timestamp()-stat.st_mtime
        if stat.st_uid!=0 or stat.st_mode&0o022 or not 0<=age_seconds<=36*3600:return None
        if not 0<stat.st_size<=4*1024**3:raise ValueError("invalid native ciphertext size")
        with dest.open("wb") as out:shutil.copyfileobj(src,out,1024*1024)
    if dest.stat().st_size!=stat.st_size:raise ValueError("native snapshot changed during copy")
    return dest

def video_entries():
    """Read a complete immutable snapshot under the publisher's shared lock."""
    lock_path=VIDEO_BASE/"publish.lock"
    if not lock_path.is_file():return None
    with lock_path.open("rb") as gate:
        fcntl.flock(gate,fcntl.LOCK_SH)
        source=VIDEO_BASE/"current"
        meta=read_json(safe_path(source,"index.json"))
        if meta is None:return
        if meta.get("format")!=1:raise ValueError("invalid video snapshot")
        stamp=datetime.fromisoformat(meta["created_at"])
        elapsed=(datetime.now(timezone.utc)-stamp).total_seconds()
        if not 0<=elapsed<=36*3600:return None
        files=[("index.json",safe_path(source,"index.json"),None),
               ("database.dump",safe_path(source,"database.dump"),meta["database_sha256"]),
               ("settings.json",safe_path(source,"settings.json"),meta["settings_sha256"])]
        seen=set()
        for item in meta["files"]:
            key=item["key"]
            if not re.fullmatch(r"[0-9a-f]{64}",key) or key in seen or hashlib.sha256(item["path"].encode()).hexdigest()!=key:
                raise ValueError("invalid video inventory")
            seen.add(key)
            p=safe_path(source,"files/"+key)
            if not p.is_file() or p.stat().st_size!=item["size"]:raise ValueError("video file unavailable")
            files.append(("files/"+key,p,item["sha256"]))
        # Generator holds lock while main backup consumes and encrypts the files.
        for name,p,sha in files:
            if not p.is_file() or (sha and digest(p)!=sha):raise ValueError("video snapshot checksum mismatch")
        for name,p,sha in files:
            yield VIDEO_PREFIX+name,p,sha

def publish_snapshot_commits(repo, env, batch_bytes=256*1024*1024):
    """Upload large encrypted deltas in bounded staging pushes; only publish main last."""
    def git(*args):
        return run(["git",*args],cwd=repo,env=env)
    def commit(message):
        git("-c","user.name=微光数学备份","-c","user.email=backup@localhost",
            "-c","commit.gpgsign=false","commit","-m",message)
    paths=set()
    for args in (("diff","--name-only","--no-renames","-z","HEAD"),("ls-files","--others","--exclude-standard","-z")):
        paths.update(p.decode("utf-8") for p in git(*args).split(b"\0") if p)
    if MANIFEST not in paths:raise ValueError("backup manifest not changed")
    sizes={name:(safe_path(repo,name).stat().st_size if safe_path(repo,name).exists() else 0) for name in paths}
    if sum(sizes.values())<=batch_bytes and len(paths)<=256:
        git("add","-A")
        commit("Encrypted business backup "+now())
        git("push","origin","HEAD:refs/heads/main")
        return
    stage="refs/heads/wg-backup-stage-"+uuid4().hex
    group=[];size=0;number=0
    def push_group(items):
        nonlocal number
        git("add","-A","--",*items)
        number+=1
        commit("Encrypted backup staging "+str(number))
        git("push","origin","HEAD:"+stage)
    try:
        for name in sorted(paths-{MANIFEST}):
            if group and (size+sizes[name]>batch_bytes or len(group)>=256):
                push_group(group);group=[];size=0
            group.append(name);size+=sizes[name]
        if group:push_group(group)
        git("add","--",MANIFEST)
        commit("Encrypted business backup "+now())
        git("push","origin","HEAD:"+stage)
        # The remote already has every encrypted blob through the staging branch.
        # A normal fast-forward push rejects concurrent changes instead of overwriting them.
        git("push","origin","HEAD:refs/heads/main")
    finally:
        # This uniquely named branch belongs only to the current attempt. If cleanup
        # fails, leave the old/new verified main untouched and permit manual inspection.
        try:
            remote=git("ls-remote","origin",stage).decode().split()
            if remote and remote[1]==stage:
                git("push","--force-with-lease="+stage+":"+remote[0],"origin",":"+stage)
        except (RuntimeError,subprocess.SubprocessError,IndexError):
            pass


def backup():
    recipient, key, hosts = config()
    env = git_env(key, hosts)
    old = read_json(STATE / "index.json", {}) or {}
    with tempfile.TemporaryDirectory(prefix="run-", dir=STATE) as d:
        work = Path(d)
        repo = work / "repo"
        run(["git", "clone", "--depth=1", "--branch=main", "--single-branch", REMOTE, str(repo)], env=env)
        prior = read_json(safe_path(repo, MANIFEST))
        if prior is not None:
            check_manifest(repo, prior, allow_legacy=True)
        previous = prior["entries"] if prior else {}
        entries, index = {}, {}
        def publish(name, path, sha=None):
            if not logical_allowed(name):
                raise ValueError("unexpected backup path")
            sha = sha or digest(path)
            prev = old.get(name, {})
            if name in previous and prev.get("sha") == sha and prev.get("recipient") == recipient and prev.get("entry") == previous[name]:
                entry = previous[name]
            else:
                encrypted = work / "cipher.age"
                encrypted.unlink(missing_ok=True)
                # Public recipient only; the decryption key is never needed on the production host.
                compressed = work / "compressed.gz"
                with path.open("rb") as src, compressed.open("wb") as dst:
                    with gzip.GzipFile(filename="", mode="wb", fileobj=dst, mtime=0) as gz:
                        shutil.copyfileobj(src, gz, 1024 * 1024)
                run(["age", "-r", recipient, "-o", str(encrypted), str(compressed)])
                compressed.unlink()
                parts = []
                with encrypted.open("rb") as f:
                    for i, chunk in enumerate(iter(lambda: f.read(CHUNK), b"")):
                        part = name + ".age." + str(i).zfill(4)
                        target = safe_path(repo, part)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(chunk)
                        parts.append({"path": part, "sha256": hashlib.sha256(chunk).hexdigest()})
                encrypted.unlink()
                entry = {"parts": parts}
            entries[name] = entry
            index[name] = {"sha": sha, "recipient": recipient, "entry": entry}
        capture(work, publish)
        video_state="not_configured" if not (VIDEO_BASE/"publish.lock").exists() else "stale"
        for name,p,sha in video_entries():
            publish(name,p,sha)
            video_state="included"
        if video_state!="included":
            # Preserve previous valid video ciphertext if the isolated snapshot is unavailable.
            for name,entry in previous.items():
                if name.startswith(VIDEO_PREFIX):
                    entries[name]=entry
                    if name in old:index[name]=old[name]
        native_state="not_configured" if not NATIVE_BASE.exists() else "stale"
        native=native_capture(work,recipient)
        if native is not None:
            publish(NATIVE_ARCHIVE,native)
            native_state="included"
        elif NATIVE_ARCHIVE in previous:
            # Retain a previous encrypted snapshot on temporary capture failure.
            entries[NATIVE_ARCHIVE]=previous[NATIVE_ARCHIVE]
            if NATIVE_ARCHIVE in old:index[NATIVE_ARCHIVE]=old[NATIVE_ARCHIVE]
            native_state="previous_retained"
        changed = entries != previous
        if changed:
            keep = {p["path"] for e in entries.values() for p in e["parts"]}
            for entry in previous.values():
                for part in entry["parts"]:
                    if part["path"] not in keep:
                        safe_path(repo, part["path"]).unlink()
            manifest = {"format": 2, "created_at": now(), "entries": entries}
            write_json(safe_path(repo, MANIFEST), manifest)
            check_manifest(repo, manifest)
            publish_snapshot_commits(repo,env)
        head = run(["git", "rev-parse", "HEAD"], cwd=repo, env=env).decode().strip()
        remote = run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=repo, env=env).decode().split()
        if not remote or remote[0] != head:
            raise RuntimeError("remote confirmation failed")
        write_json(STATE / "index.json", index)
        cipher_bytes=sum(safe_path(repo,p["path"]).stat().st_size for e in entries.values() for p in e["parts"])
        return {"state": "success" if changed else "unchanged", "at": now(), "commit": head,
                "entries": len(entries), "scope": "teaching database and registered files",
                "video_state":video_state,"native_state":native_state,"snapshot_cipher_bytes":cipher_bytes}


def restore(repo, identity, target, destination, video_destination=None, native_destination=None):
    """Restore into an explicitly named, empty rehearsal database and new file directory only."""
    import psycopg
    if not re.fullmatch(r"jiaoyan_restore_[a-z0-9_]{1,35}", target):
        raise ValueError("restore database name must start with jiaoyan_restore_")
    repo, identity = repo.resolve(), identity.resolve()
    if destination.exists() or not destination.is_absolute():
        raise ValueError("destination must be an unused absolute path")
    manifest = read_json(safe_path(repo, MANIFEST))
    check_manifest(repo, manifest, allow_legacy=True)
    video_names={n for n in manifest["entries"] if n.startswith(VIDEO_PREFIX)}
    if video_names and (video_destination is None or video_destination.exists() or not video_destination.is_absolute()):
        raise ValueError("video snapshot requires a separate unused absolute --video-files directory")
    native_present=NATIVE_ARCHIVE in manifest["entries"]
    if native_present and (native_destination is None or native_destination.exists() or not native_destination.is_absolute()):
        raise ValueError("native mirror requires a separate unused absolute --native-files directory")
    env = {k:v for k,v in os.environ.items() if not k.startswith("PG")}
    env.update(PGHOST="/var/run/postgresql", PGDATABASE=target, PGCONNECT_TIMEOUT="10")
    info = "host=/var/run/postgresql dbname=" + target + " connect_timeout=10"
    with psycopg.connect(info) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'")
            if cur.fetchone()[0]:
                raise ValueError("restore target is not empty")
    # Validate every authenticated ciphertext and stage all plaintext before touching the target.
    with tempfile.TemporaryDirectory(prefix="jiaoyan-restore-") as d:
        work = Path(d)
        for name, entry in manifest["entries"].items():
            enc = work / "cipher.age"
            with enc.open("wb") as out:
                for p in entry["parts"]:
                    with safe_path(repo, p["path"]).open("rb") as f:
                        for chunk in iter(lambda: f.read(1024*1024), b""):
                            out.write(chunk)
            plain = safe_path(work, name)
            plain.parent.mkdir(parents=True, exist_ok=True)
            compressed = work / "compressed.gz"
            run(["age", "-d", "-i", str(identity), "-o", str(compressed), str(enc)])
            with gzip.open(compressed, "rb") as src, plain.open("wb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
            compressed.unlink()
            enc.unlink()
        if native_present:
            # Verify the inner age envelope before changing the rehearsal DB.
            run(["age","-d","-i",str(identity),"-o",str(work/"native-verified.tar.gz"),str(work/NATIVE_ARCHIVE)])
            import importlib.util
            spec=importlib.util.spec_from_file_location("native_verify",Path(__file__).with_name("verify-native-backup.py"))
            verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
            staged=work/"native-verified";staged.mkdir(mode=0o700)
            verifier.inspect_archive(work/"native-verified.tar.gz",staged)
        run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "--single-transaction", "-f", str(work / SCHEMAS[0])], env=env)
        with psycopg.connect(info) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                restored_tables={r[0] for r in cur.fetchall()}
                expected_tables={table for name,table in FIXED.items() if name in manifest['entries']} | EXCLUDED
                if restored_tables != expected_tables:raise ValueError('restored schema and backup inventory mismatch')
                for name, table in FIXED.items():
                    if name not in manifest['entries']:continue
                    with (work / name).open("rb") as f, cur.copy("COPY public." + table + " FROM STDIN WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')") as cp:
                        for chunk in iter(lambda: f.read(1024*1024), b""):
                            cp.write(chunk)
                cur.execute("SELECT setval(pg_get_serial_sequence('public.audit_logs','id'), COALESCE(max(id),1), count(*)>0) FROM public.audit_logs")
                # Check decrypted attachments against restored database metadata before constraints are installed.
                cur.execute("SELECT storage_key,sha256,size_bytes FROM public.files WHERE to_jsonb(files)->>'purged_at' IS NULL")
                expected = set()
                for key, sha, size in cur.fetchall():
                    match = FILE_KEY.fullmatch(key)
                    if not match:
                        raise ValueError("invalid storage key")
                    name = "files/" + ("originals" if match[1] == "original" else "assets") + "/" + match[2]
                    p = safe_path(work, name)
                    if p.stat().st_size != size or digest(p) != sha:
                        raise ValueError("restored attachment checksum mismatch")
                    expected.add(name)
                if expected != {n for n in manifest["entries"] if n not in FIXED and n not in SCHEMAS and n not in video_names and n!=NATIVE_ARCHIVE}:
                    raise ValueError("attachment inventory mismatch")
        if video_names:
            src=work/VIDEO_PREFIX
            meta=read_json(src/"index.json")
            if meta.get("format")!=1 or digest(src/"database.dump")!=meta["database_sha256"] or digest(src/"settings.json")!=meta["settings_sha256"]:
                raise ValueError("video metadata checksum mismatch")
            paths=set()
            keys=set()
            for item in meta["files"]:
                rel=item["path"];key=item["key"]
                if not re.fullmatch(r"[0-9a-f]{64}",key) or hashlib.sha256(rel.encode()).hexdigest()!=key or key in keys:
                    raise ValueError("invalid video file inventory")
                if not any(rel.startswith(x+"/") for x in ("questions/lessons","questions/exports","images/uploads","images/assets","videos/generated","videos/imported","videos/approved")) or rel in paths:
                    raise ValueError("invalid video relative path")
                safe_path(video_destination/"storage",rel)
                p=safe_path(src,"files/"+key)
                if p.stat().st_size!=item["size"] or digest(p)!=item["sha256"]:raise ValueError("restored video checksum mismatch")
                paths.add(rel);keys.add(key)
            if video_names!={VIDEO_PREFIX+x for x in ("index.json","database.dump","settings.json")}|{VIDEO_PREFIX+"files/"+key for key in keys}:
                raise ValueError("video inventory mismatch")
            video_destination.mkdir(mode=0o700)
            for name in ("database.dump","settings.json","index.json"):
                shutil.copyfile(src/name,video_destination/name)
            for item in meta["files"]:
                out=safe_path(video_destination/"storage",item["path"])
                out.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                shutil.copyfile(src/"files"/item["key"],out)
        run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "--single-transaction", "-f", str(work / SCHEMAS[1])], env=env)
        destination.mkdir(mode=0o700, parents=False)
        for name in expected:
            sub, ident = name.split("/")[1:]
            out = destination / ("original" if sub == "originals" else "generated") / ident
            out.parent.mkdir(mode=0o700, exist_ok=True)
            # Temporary directory may be on a different filesystem.
            shutil.copyfile(work / name, out)
            out.chmod(0o600)
        if native_present:
            native_destination.mkdir(mode=0o700)
            shutil.copyfile(work/NATIVE_ARCHIVE,native_destination/"mirror.tar.gz.age")
            (native_destination/"mirror.tar.gz.age").chmod(0o600)
    print("Rehearsal restored. Create a new administrator; never switch production automatically.")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("backup")
    r = sub.add_parser("restore")
    r.add_argument("--repo", type=Path, required=True)
    r.add_argument("--identity", type=Path, required=True)
    r.add_argument("--database", required=True)
    r.add_argument("--files", type=Path, required=True)
    r.add_argument("--video-files", type=Path)
    r.add_argument("--native-files", type=Path)
    args = parser.parse_args()
    if args.action == "restore":
        restore(args.repo, args.identity, args.database, args.files,args.video_files,args.native_files)
        return
    STATE.mkdir(mode=0o700, exist_ok=True)
    if STATE.is_symlink() or STATE.stat().st_mode & 0o077:
        raise SystemExit("backup state directory must be private")
    with (STATE / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        write_json(STATE / "status.json", {"state": "running", "at": now()})
        try:
            result = backup()
            write_json(STATE / "last-success.json", result)
            write_json(STATE / "status.json", result)
            print("Backup " + result["state"] + ": " + result["commit"])
        except Exception as exc:
            # Never print raw subprocess output, config values, file names or DB rows.
            write_json(STATE / "status.json", {"state": "failed", "at": now(), "error": type(exc).__name__})
            print("Backup failed: " + type(exc).__name__)
            raise SystemExit(1) from None


if __name__ == "__main__":
    main()
