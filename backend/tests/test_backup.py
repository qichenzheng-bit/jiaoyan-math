"""Backup contract tests: no access to production DB, credentials, or GitHub."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
from app.core.db import Base
import app.models  # noqa: F401

spec = importlib.util.spec_from_file_location("backup_script", Path(__file__).resolve().parents[2] / "deploy" / "backup.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def test_inventory_covers_model_tables():
    assert backup.TABLES == set(Base.metadata.tables) | {"alembic_version"}
    assert not (backup.EXCLUDED & set(backup.FIXED.values()))
    assert len(backup.FIXED) == len(backup.EXPORTS) + 3


def test_checkin_never_restores_auto_or_pat():
    value = backup.sanitize_checkin(json.dumps({
        "enabled": True, "pat": "secret", "quota_attempt_at": 123,
        "history": [{"state":"claimed","earned":100,"pat":"hidden"}],
        "archives": [{"history": [{"state":"claimed","token":"hidden"}]}],
    }))
    data = json.loads(value)
    assert data["enabled"] is False
    assert data["history"] == [{"state":"claimed","earned":100}]
    assert "secret" not in value and "hidden" not in value
    assert "quota_attempt_at" not in data


def test_manifest_checks_integrity_and_paths(tmp_path):
    entries = {}
    for name in set(backup.FIXED) | set(backup.SCHEMAS):
        part = name + ".age.0000"
        path = tmp_path / part
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"ciphertext")
        entries[name] = {"parts": [{"path":part,"sha256":hashlib.sha256(b"ciphertext").hexdigest()}]}
    manifest = {"format":2,"entries":entries}
    backup.check_manifest(tmp_path, manifest)
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="verification"):
        backup.check_manifest(tmp_path, manifest)
    with pytest.raises(ValueError):
        backup.safe_path(tmp_path, "../escape")
    (tmp_path / "alias").symlink_to(tmp_path / "database", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        backup.safe_path(tmp_path, "alias/file")


def test_restore_rejects_production_database(tmp_path):
    with pytest.raises(ValueError, match="restore database name"):
        backup.restore(tmp_path, tmp_path/"identity", "jiaoyan", tmp_path/"files")


def test_legacy_manifest_work_group_is_all_or_nothing(tmp_path):
    entries={}
    for name in (set(backup.FIXED)|set(backup.SCHEMAS))-backup.WORK_EXPORTS:
        part=name+".age.0000"
        path=tmp_path/part;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b"data")
        entries[name]={"parts":[{"path":part,"sha256":hashlib.sha256(b"data").hexdigest()}]}
    manifest={"format":2,"entries":entries}
    with pytest.raises(ValueError,match="incomplete"):backup.check_manifest(tmp_path,manifest)
    backup.check_manifest(tmp_path,manifest,allow_legacy=True)
    entries.pop("database/schema-pre.sql")
    with pytest.raises(ValueError,match="incomplete"):backup.check_manifest(tmp_path,manifest,allow_legacy=True)


def test_original_purge_lock_matches_backup():
    from app.services import storage
    assert storage.PURGE_LOCK==backup.PURGE_LOCK

def test_legacy_source_catalog_manifest(tmp_path):
    entries={}
    for name in (set(backup.FIXED)|set(backup.SCHEMAS))-backup.CATALOG_EXPORTS:
        part=name+".age.0000"
        path=tmp_path/part;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b"data")
        entries[name]={"parts":[{"path":part,"sha256":hashlib.sha256(b"data").hexdigest()}]}
    manifest={"format":2,"entries":entries}
    with pytest.raises(ValueError,match="incomplete"):backup.check_manifest(tmp_path,manifest)
    backup.check_manifest(tmp_path,manifest,allow_legacy=True)
    assert backup.CATALOG_EXPORTS=={"teaching/sources/catalog_details.csv"}


def test_video_logical_paths_are_opaque_and_bounded():
    assert backup.logical_allowed("production/video-engine/index.json")
    assert backup.logical_allowed("production/video-engine/files/"+"a"*64)
    assert not backup.logical_allowed("production/video-engine/files/../../secret")
    assert not backup.logical_allowed("production/video-engine/engine.env")


def test_large_backup_staging_keeps_main_atomic(tmp_path):
    import os
    import subprocess
    remote=tmp_path/"remote.git"
    work=tmp_path/"work"
    work.mkdir()
    def git(*args,cwd=work):
        return subprocess.check_output(["git",*args],cwd=cwd)
    git("init","--bare",str(remote),cwd=tmp_path)
    git("init","-b","main")
    git("config","user.name","Test")
    git("config","user.email","test@example.invalid")
    (work/"README").write_text("initial")
    git("add",".")
    git("commit","-m","initial")
    git("remote","add","origin",str(remote))
    git("push","origin","main")
    old=git("rev-parse","HEAD").strip()
    for i in range(3):
        (work/("part"+str(i))).write_bytes(b"encrypted payload")
    manifest=work/backup.MANIFEST
    manifest.parent.mkdir()
    manifest.write_text('{"test":true}')
    backup.publish_snapshot_commits(work,dict(os.environ),batch_bytes=20)
    head=git("rev-parse","HEAD").strip()
    assert head!=old
    assert git("ls-remote","origin","refs/heads/main").split()[0]==head
    assert not git("ls-remote","origin","refs/heads/wg-backup-stage-*").strip()
    assert git("show","HEAD:"+backup.MANIFEST).strip()==b'{"test":true}'


def test_native_backup_verifies_private_mirror_and_rejects_paths(tmp_path):
    import io
    import sqlite3
    import tarfile
    from uuid import uuid4
    spec=importlib.util.spec_from_file_location("native_verify",Path(__file__).resolve().parents[2]/"deploy"/"verify-native-backup.py")
    verify=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)
    sid=str(uuid4());root=tmp_path/"source";ws=root/".jiaoyan-native-workspaces"/sid
    ws.mkdir(parents=True)
    (ws/"owner").write_text("1")
    (ws/"sessions.json").write_text(json.dumps({"sessions":[sid],"jobs":[]}))
    db=sqlite3.connect(ws/"session-mirror.sqlite3")
    db.execute("CREATE TABLE entries(payload TEXT)")
    db.execute("INSERT INTO entries VALUES ('{}')");db.commit();db.close()
    archive=tmp_path/"valid.tar.gz"
    with tarfile.open(archive,"w:gz") as tar:tar.add(root/".jiaoyan-native-workspaces",arcname=".jiaoyan-native-workspaces")
    stage=tmp_path/"stage";stage.mkdir()
    result=verify.inspect_archive(archive,stage)
    assert result["mirrors"]==1 and result["transcript_entries"]==1
    bad=tmp_path/"bad.tar.gz"
    with tarfile.open(bad,"w:gz") as tar:
        entry=tarfile.TarInfo("../credential");entry.size=1;tar.addfile(entry,io.BytesIO(b"x"))
    with pytest.raises(ValueError,match="unexpected"):verify.inspect_archive(bad,tmp_path/"badstage")
    assert not verify.allowed(".jiaoyan-native-workspaces/"+sid+"/.qoder-cn/settings.json",False)


def test_native_snapshot_path_is_exact():
    assert backup.logical_allowed(backup.NATIVE_ARCHIVE)
    assert not backup.logical_allowed("ai/native-state/credentials")
    assert not backup.logical_allowed("ai/native-state/../secret")

def test_native_online_snapshot_excludes_smoke_and_login(tmp_path):
    import sqlite3
    from uuid import uuid4
    spec=importlib.util.spec_from_file_location("native_capture",Path(__file__).resolve().parents[2]/"deploy"/"snapshot-native-state.py")
    capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
    home=tmp_path/"home";work=home/".jiaoyan-native-workspaces";sid=str(uuid4())
    for owner,ident in [("1",sid),(capture.SMOKE_OWNER,str(uuid4()))]:
        ws=work/ident;ws.mkdir(parents=True)
        (ws/"owner").write_text(owner)
        (ws/"sessions.json").write_text(json.dumps({"sessions":[ident],"jobs":[]}))
        db=sqlite3.connect(ws/"session-mirror.sqlite3")
        db.execute("CREATE TABLE entries(payload TEXT)")
        db.execute("INSERT INTO entries VALUES ('{}')");db.commit();db.close()
        (ws/"unrelated-token").write_text("do not copy")
    (home/".qoder-cn").mkdir()
    (home/".qoder-cn"/"auth").write_text("not copied")
    stage=tmp_path/"stage";stage.mkdir()
    capture.collect(home,stage)
    result=stage/work.name/sid
    assert result.is_dir() and (result/"session-mirror.sqlite3").exists()
    assert len(list((stage/work.name).iterdir()))==1
    assert not (result/"unrelated-token").exists() and not (stage/".qoder-cn").exists()


def test_native_chat_anchor_is_terminal_and_only_contains_identity():
    from uuid import uuid4
    workspace,sid,job=map(str,[uuid4(),uuid4(),uuid4()])
    state={"native":True,"phase":"terminal","native_actor":1,"workspace":workspace,"native_session":sid,"job":job,"prompt":"secret","steps":[{"args":"secret"}]}
    clean=json.loads(backup.native_chat_anchor(json.dumps(state),workspace))
    assert clean["native_session"]==sid and "prompt" not in clean and "steps" not in clean
    assert backup.native_chat_anchor(json.dumps({**state,"phase":"model"}),workspace) is None
    assert backup.native_chat_anchor(json.dumps(state),str(uuid4())) is None


def test_history_cleanup_marker_is_preserved_in_backup():
    from app.services.history_cleanup import KEY
    assert KEY in backup.SAFE_SETTINGS

def test_real_age_roundtrip_native_mirror(tmp_path):
    """Actual encryption/decryption with an ephemeral CI key, never a production identity."""
    import io
    import os
    import shutil
    import sqlite3
    import subprocess
    import sys
    import tarfile
    from uuid import uuid4
    if not shutil.which("age") or not shutil.which("age-keygen"):
        if os.environ.get("WG_REQUIRE_AGE_TEST")=="1":pytest.fail("age is required for recovery rehearsal")
        pytest.skip("age is not installed")
    deploy=Path(__file__).resolve().parents[2]/"deploy"
    spec=importlib.util.spec_from_file_location("capture_roundtrip",deploy/"snapshot-native-state.py")
    capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
    sid=str(uuid4());home=tmp_path/"home";ws=home/".jiaoyan-native-workspaces"/sid;ws.mkdir(parents=True)
    (ws/"owner").write_text("1")
    (ws/"sessions.json").write_text(json.dumps({"sessions":[sid],"jobs":[]}))
    db=sqlite3.connect(ws/"session-mirror.sqlite3")
    db.execute("CREATE TABLE entries(payload TEXT)")
    db.execute("INSERT INTO entries VALUES (?)",("synthetic-session",));db.commit();db.close()
    stage=tmp_path/"stage";stage.mkdir()
    capture.collect(home,stage)
    archive=tmp_path/"mirror.tar.gz"
    with tarfile.open(archive,"w:gz") as tar:
        for p in stage.iterdir():tar.add(p,arcname=p.name)
    identity=tmp_path/"identity"
    subprocess.run(["age-keygen","-o",str(identity)],check=True,capture_output=True)
    recipient=subprocess.check_output(["age-keygen","-y",str(identity)],text=True).strip()
    cipher=tmp_path/"mirror.age"
    subprocess.run(["age","-r",recipient,"-o",str(cipher),str(archive)],check=True)
    assert b"synthetic-session" not in cipher.read_bytes()
    result=subprocess.run([sys.executable,str(deploy/"verify-native-backup.py"),"--archive",str(cipher),"--identity",str(identity)],check=True,capture_output=True,text=True)
    report=json.loads(result.stdout)
    assert report["status"]=="ARCHIVE_VERIFIED" and report["mirrors"]==1 and report["transcript_entries"]==1
    tampered=tmp_path/"tampered.age"
    data=cipher.read_bytes();tampered.write_bytes(data[:-1]+bytes([data[-1]^1]))
    invalid=subprocess.run([sys.executable,str(deploy/"verify-native-backup.py"),"--archive",str(tampered),"--identity",str(identity)],capture_output=True)
    assert invalid.returncode!=0
