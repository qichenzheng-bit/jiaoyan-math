"""100,000-row synthetic benchmark in the isolated CI database, always rolled back."""
import os
from time import perf_counter
from statistics import median
from uuid import uuid4
import pytest
from sqlalchemy import insert, select, func, text
from app.core.db import engine,session_factory
from app.models import TeachingResource
from app.core.search_features import search_features
from app.core.content_normalization import question_fingerprint,question_stem_key
from app.core.question_matching import search
from app.core.bank_filter_facts import filter_facts

@pytest.mark.skipif(os.environ.get("RUN_POSTGRES_INTEGRATION")!="1",reason="isolated PostgreSQL only")
def test_indexed_search_100k():
    assert engine().url.database=="jiaoyan_ci"
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("alembic.ini"),"head")
    prefix=uuid4().hex[:8]
    target=r"求此不定积分 $\int xe^{x}\,\mathrm{d}x$"
    variant=r"求此不定积分 $\int xe^{2}\,\mathrm{d}x$"
    templates=["掷骰子随机事件甲出现次数为{}","求向量组秩并判断线性相关性参数{}","给定三维几何平面距离{}","讨论分布律及随机变量的期望参数{}","已知矩阵的迹及特征向量参数{}","计算二次型的正负惯性指数{}"]
    def row(i,body,answer="",solution="",updated=1):
        return dict(id=prefix+str(i).zfill(12),code="B"+prefix+str(i).zfill(6),kind="question",title="合成检索样本",subject="高等数学",content=body,answer=answer,solution=solution,tags=[],fingerprint=question_fingerprint(body,solution,answer),stem_key=question_stem_key(body),search_features=search_features(body),bank_facts=filter_facts(body,answer,solution,""),archived=False,created_at=updated,updated_at=updated)
    with session_factory()() as db:
        # A single transaction: never leave synthetic questions in the library.
        for offset in range(0,100000,2000):
            db.execute(insert(TeachingResource.__table__),[row(i,templates[i%len(templates)].format(i),updated=2+i) for i in range(offset,offset+2000)])
        exact=row(100000,target,"0","分部积分法");near=row(100001,variant,"1","方法二")
        db.execute(insert(TeachingResource.__table__),[exact,near])
        db.execute(text("ANALYZE teaching_resources"))
        total=db.scalar(select(func.count()).select_from(TeachingResource).where(TeachingResource.kind=="question",TeachingResource.archived==False))
        assert total>=100002
        durations=[]
        for _ in range(5):
            start=perf_counter();hits,scanned=search(db,"question",target,"0","新方法");durations.append(perf_counter()-start)
            categories={x["resource"].id:x["category"] for x in hits}
            assert categories.get(exact["id"])=="new_method"
            assert categories.get(near["id"])=="similar"
            assert scanned<total//10
        print(f"QUESTION_SEARCH_100K rows={total} scanned={scanned} median_ms={median(durations)*1000:.1f} max_ms={max(durations)*1000:.1f}")
        assert max(durations)<20, "Selective indexed synthetic retrieval exceeded 20s"
        from app.api.resources import listing
        from inspect import signature
        from fastapi.params import Query
        defaults={name:parameter.default.default for name,parameter in signature(listing).parameters.items() if isinstance(parameter.default,Query)}
        defaults.update(kind="question",bank_summary=True,method_name="分部积分",integrity="complete",limit=20,db=db)
        times=[]
        for _ in range(5):
            t=perf_counter();result=listing(**defaults);times.append(perf_counter()-t)
            assert exact["id"] in {r["id"] for r in result["items"]}
        print(f"BANK_FILTER_100K rows={total} median_ms={median(times)*1000:.1f} max_ms={max(times)*1000:.1f}")
        assert max(times)<20
        db.rollback()
