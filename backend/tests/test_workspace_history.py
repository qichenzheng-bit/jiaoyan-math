from types import SimpleNamespace
from app.api.workspaces import session_view

def test_agent_intake_children_are_grouped_under_parent():
    s=SimpleNamespace(id="w",title="录入试卷",created_at=1,updated_at=2,agent_history=[{"child":{"kind":"intake","id":"j1"},"steps":[{"tool":"intake_text","result":{"id":"j1"}},{"tool":"intake_text","result":{"id":"j2"}},{"tool":"other","result":{"id":"other"}}]}])
    assert session_view(s)["intake_job_ids"]==["j1","j2"]
