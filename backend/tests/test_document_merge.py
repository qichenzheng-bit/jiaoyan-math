import pytest
from app.core.document_merge import merge_document, MergeConflict

def doc(**changes):
    return {"title":"卷","kind":"paper","subject":"","source_id":None,"blocks":[{"uid":"a","kind":"reference","resource_id":"q","answer":"","score":0,"subquestion_scores":[],"local_fields":[]}],**changes}

def test_disjoint_fields():
    b=doc();l=doc(title="新标题");r=doc()
    r["blocks"][0]["score"]=5
    out=merge_document(b,l,r)
    assert out["title"]=="新标题" and out["blocks"][0]["score"]==5

def test_same_field_conflict_and_deleted_edited_block():
    b=doc();l=doc(title="甲");r=doc(title="乙")
    with pytest.raises(MergeConflict):merge_document(b,l,r)
    l=doc(blocks=[]);r=doc();r["blocks"][0]["answer"]="新答案"
    with pytest.raises(MergeConflict):merge_document(b,l,r)

def test_independent_fields_same_block():
    b=doc();l=doc();r=doc()
    l["blocks"][0]["score"]=6
    r["blocks"][0]["answer"]="答案"
    out=merge_document(b,l,r)["blocks"][0]
    assert out["score"]==6 and out["answer"]=="答案"
