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

@pytest.mark.skipif(os.environ.get("RUN_POSTGRES_INTEGRATION")!="1",reason="isolated PostgreSQL only")
def test_question_bank_pressure_500k():
    """Synthetic SQL list and filter pressure; not a claim about production hardware."""
    assert engine().url.database=="jiaoyan_ci"
    from alembic import command
    from alembic.config import Config
    from inspect import signature
    from fastapi.params import Query
    from app.api.resources import listing
    command.upgrade(Config("alembic.ini"),"head")
    prefix=uuid4().hex[:7]
    with session_factory()() as db:
        # Separate synthetic sources with a known exact distribution.
        db.execute(text("""
          INSERT INTO teaching_resources(id,code,kind,title,subject,content,answer,solution,tags,exams,
            fingerprint,stem_key,archived,created_at,updated_at,source_type,cohort_year,exam_type)
          SELECT :prefix||'s'||g::text,'S'||:prefix||lpad(g::text,5,'0'),'source','合成试卷','',
            '合成原件','','','[]'::json,'[]'::json,md5(:prefix||'s'||g::text),'',false,1,1,'exam',
            CASE WHEN g%2=0 THEN '2026' ELSE '2025' END,'数学一'
          FROM generate_series(0,99) g
        """),{"prefix":prefix})
        previous=0
        for n in (1000,10000,100000,500000):
            db.execute(text("""
              INSERT INTO teaching_resources(id,code,kind,title,subject,content,answer,solution,tags,exams,
                fingerprint,stem_key,search_features,bank_facts,archived,created_at,updated_at,question_type,difficulty,source_id)
              SELECT :prefix||g::text,'Z'||:prefix||lpad(g::text,7,'0'),'question','压力测试题目',
                CASE WHEN g%3=0 THEN '高等数学' ELSE '线性代数' END,
                '求参数为 '||g::text||' 的函数极限 $\\lim_{x\\to0}x$','0',CASE WHEN g%1000=0 THEN '泰勒展开' ELSE '直接代入法' END,CASE WHEN g%1000=0 THEN '["压力共同知识点","压力专项知识点"]'::json ELSE '["压力共同知识点"]'::json END,'[]'::json,
                md5(:prefix||g::text),md5(:prefix||g::text),'{}'::jsonb,
                CASE WHEN g%1000=0 THEN '{"answer_complete": true,"solution_complete": true,"ambiguous": false,"method:泰勒展开": true,"single": true}'::jsonb
                  ELSE '{"answer_complete": true,"solution_complete": true,"ambiguous": false,"single": true}'::jsonb END,
                false,g,g,'综合题','简单',:prefix||'s'||(g%100)::text FROM generate_series(CAST(:start AS integer),CAST(:end AS integer)) g
            """),{"prefix":prefix,"start":previous+1,"end":n})
            previous=n
            db.execute(text("ANALYZE teaching_resources"))
            defaults={name:parameter.default.default for name,parameter in signature(listing).parameters.items() if isinstance(parameter.default,Query)}
            defaults.update(kind="question",bank_summary=True,compact=True,limit=20,db=db)
            ordinary=[];combined=[]
            for _ in range(3):
                t=perf_counter();a=listing(**defaults);ordinary.append(perf_counter()-t)
                t=perf_counter();b=listing(**{**defaults,"subject":"高等数学","method_name":"泰勒公式","integrity":"complete"});combined.append(perf_counter()-t)
                assert a["total"]>=n and len(a["items"])==20 and b["total"]>=n//3000
            print(f"BANK_PRESSURE rows={n} list_median_ms={median(ordinary)*1000:.1f} filter_median_ms={median(combined)*1000:.1f}")
            assert max(ordinary+combined)<20,"synthetic database query exceeded 20 seconds"
        # Duplicate primary relation plus one secondary source for every tenth question.
        db.execute(text("""
          INSERT INTO resource_source_links(resource_id,source_id,provenance_role,original_question_number,
            chapter,note,is_primary,role_verified,occurrences)
          SELECT :prefix||g::text,:prefix||'s'||(g%100)::text,'original','','','',true,true,'[]'::json
          FROM generate_series(10,500000,10) g
          UNION ALL
          SELECT :prefix||g::text,:prefix||'s'||((g+1)%100)::text,'reproduced','','','',false,true,'[]'::json
          FROM generate_series(10,500000,10) g
        """),{"prefix":prefix})
        db.execute(text("ANALYZE resource_source_links"))
        db.execute(text("ANALYZE teaching_resources"))
        from app.api.source_catalog import (statistics,statistics_questions,statistics_report,distribution,
            StatisticsRequest,StatisticsQuestions,StatisticsReport,DistributionRequest)
        scope={"source_ids":[prefix+"s"+str(i) for i in range(100)]}
        timings={}
        for label,call in (
            ("knowledge",lambda:statistics(StatisticsRequest(**scope),db)),
            ("drill",lambda:statistics_questions(StatisticsQuestions(**scope,knowledge_name="压力专项知识点",knowledge_subject="高等数学"),db)),
            ("year",lambda:statistics_report(StatisticsReport(**scope,dimension="year"),db)),
            ("cooccurrence",lambda:distribution(DistributionRequest(**scope,dimension="cooccurrence",knowledge_name="压力专项知识点",knowledge_subject="高等数学"),db)),
        ):
            elapsed=[]
            for _ in range(3):
                start=perf_counter();result=call();elapsed.append(perf_counter()-start)
                if label=="knowledge":
                    assert result["question_count"]==500000 and result["source_question_count"]==550000
                    assert result["knowledge_count"]==4
                elif label=="drill":assert result["total"]==166
                elif label=="year":assert result["total"]==2 and sum(r["source_question_count"] for r in result["items"])==550000
                else:assert result["question_count"]==166 and result["items"][0]["question_count"]==166
            timings[label]={"median_ms":round(median(elapsed)*1000,1),"max_ms":round(max(elapsed)*1000,1)}
            assert max(elapsed)<30,"synthetic statistics query exceeded 30 seconds"
        print("SOURCE_STATISTICS_500K",timings)
        db.rollback()
