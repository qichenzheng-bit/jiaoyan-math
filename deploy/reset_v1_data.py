#!/usr/bin/env python3
"""One-time owner-authorized V1 production reset. No database/schema or credential deletion."""
import argparse
import json
import os
from pathlib import Path
import shutil
import psycopg
from psycopg import sql

KEY = "system.v1.initial_data_reset"
PRESERVE = ("users", "sessions", "settings", "alembic_version")
BUSINESS = ["files","audit_logs","file_references","teaching_resources","chat_sessions","chat_messages","resource_source_links","resource_source_versions","source_catalog_details","knowledge_point_catalog","resource_knowledge_links","knowledge_aliases","knowledge_relations","teaching_documents","teaching_document_versions","document_registrations","document_ai_edits","document_resource_refs","intake_imports","intake_jobs","intake_supplements","studio_items","studio_revisions","video_projects","work_sessions","work_materials","work_batches","teaching_works","teaching_work_versions","teaching_work_assets","teaching_work_pending_covers"]
CONFIG_KEYS = ("display_name", "theme", "ai.qoder.model", "ai.qoder.video_model",
               "ai.qoder.effort", "ai.qoder.video_effort")
CHECKIN = "qiandao.qoder_cn.v1"
FOLDERS = ("original", "generated", ".staging")

def reset_status(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM public.settings WHERE key=%s", (KEY,))
        row=cur.fetchone()
    result=row[0] if row else "new"
    if result not in ("new","pending-files","done"):
        raise RuntimeError("unknown reset status")
    return result

def verify_root(path):
    if path.is_symlink() or path.resolve()!=path or not path.is_dir():
        raise RuntimeError("unsafe application file storage")
    for folder in FOLDERS:
        p=path/folder
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            raise RuntimeError("unsafe application file directory")

def set_status(cur, state):
    cur.execute("INSERT INTO public.settings (key,value) VALUES (%s,%s) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value", (KEY,state))

def reset_database(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        actual={r[0] for r in cur.fetchall()}
        if actual!=set(BUSINESS)|set(PRESERVE):
            raise RuntimeError("database tables differ from reviewed V1 schema")
        cur.execute("SELECT pg_advisory_xact_lock(824650219)")
        if reset_status(conn)!="new":
            raise RuntimeError("unexpected reset status")
        cur.execute("SELECT value FROM public.settings WHERE key=%s",(CHECKIN,))
        row=cur.fetchone()
        enabled=False
        if row:
            try:enabled=json.loads(row[0]).get("enabled") is True
            except (ValueError,AttributeError):pass
        # No CASCADE: any unexpected FK to preserved account tables must fail closed.
        cur.execute(sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY").format(
            sql.SQL(",").join(sql.Identifier("public",t) for t in BUSINESS)))
        cur.execute("DELETE FROM public.settings WHERE NOT (key=ANY(%s) OR "
                    "key ~ '^ai[.]prompt[.][0-9]+[.](global|chat|work|intake|document|video|cover)$')",
                    (list(CONFIG_KEYS),))
        if enabled:
            cur.execute("INSERT INTO public.settings (key,value) VALUES (%s,%s)",
                        (CHECKIN,json.dumps({"enabled":True,"history":[]})))
        set_status(cur,"pending-files")
    conn.commit()

def finish_files(conn, root):
    if reset_status(conn)!="pending-files":
        raise RuntimeError("reset not pending")
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(824650219)")
        for table in BUSINESS:
            cur.execute(sql.SQL("SELECT EXISTS (SELECT 1 FROM {})").format(sql.Identifier("public",table)))
            if cur.fetchone()[0]:
                raise RuntimeError("new business data exists; refusing to delete files")
        verify_root(root)
        for folder in FOLDERS:
            path=root/folder
            if path.exists():shutil.rmtree(path)
            path.mkdir(mode=0o700)
        set_status(cur,"done")
    conn.commit()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("status","reset"))
    args=parser.parse_args()
    dsn=os.environ["DATABASE_URL"].replace("postgresql+psycopg://","postgresql://",1)
    root=Path(os.environ["STORAGE_ROOT"])
    if root!=Path.home()/"jiaoyan-app/data/files":
        raise RuntimeError("not the provisioned V1 production storage root")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(),current_user")
            if cur.fetchone()!=("jiaoyan","jiaoyan"):
                raise RuntimeError("not the dedicated V1 production database")
        status=reset_status(conn)
        if args.action=="status":
            print(status)
            return
        if status=="done":
            print("V1 reset already completed; new data untouched")
            return
        verify_root(root)
        if status=="new":reset_database(conn)
        finish_files(conn,root)
        print("V1 application data reset complete")

if __name__=="__main__":
    main()
