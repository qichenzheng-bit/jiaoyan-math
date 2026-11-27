"""Recover a durable PDF job after losing all process-local state."""
from pathlib import Path
import threading
from app.api import document_pdf as queue

class Executor:
    def __init__(self):self.submissions=[]
    def submit(self,fn,job):self.submissions.append((fn,job.id))

def test_pdf_queue_restarts_from_private_manifest(tmp_path,monkeypatch):
    monkeypatch.setattr(queue.storage,"root",lambda:tmp_path)
    monkeypatch.setattr(queue,"loaded_root",None)
    monkeypatch.setattr(queue,"queue_lock",None)
    monkeypatch.setattr(queue,"jobs",{})
    executor=Executor()
    monkeypatch.setattr(queue,"pool",executor)
    with queue.lock:
        root=queue.ensure_loaded()
        folder=root/"c9607118-5332-4aee-a4ee-444faa81344a"
        folder.mkdir(mode=0o700)
        job=queue.Job(folder.name,1,"doc","book","test.pdf",folder,{})
        job.payload.write_text('{"doc":{}}')
        queue.jobs[job.id]=job
        queue.change(job,state="running",stage="生成 PDF")
        # Simulate a killed process: only durable files survive.
        queue.queue_lock.close()
        queue.queue_lock=None;queue.loaded_root=None;queue.jobs={}
        queue.ensure_loaded()
        try:
            restored=queue.jobs[job.id]
            assert restored.state=="queued"
            assert restored.payload.read_text()=='{"doc":{}}'
            assert executor.submissions==[(queue.run,job.id)]
            assert restored.user_id==1
            queue.change(restored,state="ready",stage="生成完成",pages=1)
            restored.output.write_bytes(b"%PDF-1.7\n")
            queue.queue_lock.close()
            queue.queue_lock=None;queue.loaded_root=None;queue.jobs={}
            queue.ensure_loaded()
            assert queue.jobs[job.id].state=="ready"
            assert len(executor.submissions)==1
        finally:
            queue.queue_lock.close()
            queue.queue_lock=None


def test_ready_pdf_registration_failure_preserves_download(tmp_path, monkeypatch):
    import json
    from contextlib import contextmanager
    job = queue.Job("job", 1, "doc", "book", "test.pdf", tmp_path, {})
    job.payload.write_text(json.dumps({"doc":{"title":"教材","blocks":[]},"layout":{}}))
    def render(payload, images, output, stage, cancelled):
        output.write_bytes(b"%PDF-1.7\n")
        return {"pages":1,"bytes":output.stat().st_size}
    class DB:
        def commit(self): pass
    @contextmanager
    def session():
        yield DB()
    monkeypatch.setattr(queue, "render_pdf", render)
    monkeypatch.setattr(queue, "session_factory", lambda:session)
    def fail(*args, **kwargs):
        raise RuntimeError("registration failed")
    monkeypatch.setattr(queue.teaching_works,"register_pdf",fail)
    queue.run(job)
    assert job.state == "ready"
    assert job.work_id is None and job.work_error
    assert job.output.exists()
