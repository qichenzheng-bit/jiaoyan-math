"""Execute the actual scope guards without installing Manim into the web venv."""
import ast
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
path=ROOT/"vendor/video-overlay/app/backend/src/weiguang_backend/pipeline/edit_executor.py"
def guards():
    tree=ast.parse(path.read_text(encoding="utf-8"))
    names={"EditOutputError","_strip_tts_text","assert_only_tts_text_changed","validate_edit_scope_ast"}
    selected=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
    ns={"ast":ast}
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),"exec"),ns)
    return ns
BASE='class Lesson(AuthoredScene):\n    def construct(self):\n        self.start_cue("c1","得","",tts_text="dei")\n        self.end_cue("c1")\n'
def test_voice_only_and_removal():
    g=guards();check=g["assert_only_tts_text_changed"];error=g["EditOutputError"]
    before={"scene_01":BASE,"scene_02":BASE.replace("c1","c2")}
    after={**before,"scene_01":BASE.replace('"dei"','"de"')}
    check(before,after)
    with pytest.raises(error):check(before,{"scene_01":after["scene_01"]})
    with pytest.raises(error):check(before,{**after,"scene_01":after["scene_01"].replace('"得"','"改"')})
def test_out_of_scope_scene():
    g=guards();check=g["validate_edit_scope_ast"];error=g["EditOutputError"]
    before={"scene_01":BASE,"scene_02":BASE}
    check(before,{**before,"scene_01":BASE.replace("dei","de")},targets=("scene_01",))
    with pytest.raises(error):check(before,{**before,"scene_02":"bad"},targets=("scene_01",))
    with pytest.raises(error):check(before,{"scene_01":BASE},targets=("scene_01",))
    check(before,{"scene_01":BASE},targets=("scene_01",),allowed_removed=("scene_02",))
