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
