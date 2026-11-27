from types import SimpleNamespace
from app.core.method_recommendation import choices_for,apply_choices,video_solution
from app.core.solution_methods import format_methods

def test_selection_retains_all_methods_and_only_projects_recommended():
    r=SimpleNamespace(content="求导数",answer="2x",solution=format_methods([{"body":"定义法","recommended":True},{"body":"公式法","recommended":False}]),question_type="综合题",question_data=None)
    assert len(choices_for(r)[0]["methods"])==2
    r.solution,r.question_data=apply_choices(r,{"main":2})
    assert len(choices_for(r)[0]["methods"])==2
    assert video_solution(r)=="公式法"
