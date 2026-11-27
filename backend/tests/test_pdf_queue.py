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
