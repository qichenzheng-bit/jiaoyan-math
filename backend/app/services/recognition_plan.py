"""Conservative recognition instruction parsing; it only proposes a range, never executes a task."""
import re
import unicodedata
from pathlib import Path

def normalize(value):
    return unicodedata.normalize("NFKC",value).strip().casefold()

def number(value):
    if value.isdecimal():return int(value)
    if value=="两":return 2
    return "一二三四五六七八九十".index(value)+1

def parse_instruction(instruction):
    q=normalize(instruction)
    # Explicit physical pages take precedence over relative continuation.
    match=None;start=None;count=None
    for pattern,kind in [
        (r"从\s*第?\s*(\d+)\s*页\s*(?:开始|起)\s*(?:识别|处理)?\s*(\d+|[一二两三四五六七八九十])\s*页","from"),
        (r"第?\s*(\d+)\s*页?\s*(?:-|–|—|~|至|到)\s*第?\s*(\d+)\s*页","range"),
        (r"第\s*(\d+)\s*页","single"),
        (r"(?:继续|接着|接下来|后续|后面|再|识别|处理)\s*(?:识别|处理)?\s*(?:后面|后续|接下来|下面|接着|再)?\s*的?\s*(\d+|[一二两三四五六七八九十])\s*页","relative"),
    ]:
        m=re.search(pattern,q)
        if not m:continue
        match=m
        if kind=="from":start=int(m[1]);count=number(m[2])
        elif kind=="range":start=int(m[1]);count=int(m[2])-start+1
        elif kind=="single":start=int(m[1]);count=1
        else:count=number(m[1])
        break
    if not match or count is None:raise ValueError("请输入明确页数或范围，如继续识别5页、识别第21至30页")
    if not 1<=count<=10 or start is not None and not (1<=start<=10000 and start+count-1<=10000):
        raise ValueError("PDF每批只允许1–10个有效物理页")
    remainder=q[:match.start()]+" "+q[match.end():]
    if re.search(r"\d+\s*页",remainder):raise ValueError("存在多个页码指令，请一次明确一个范围")
    unfinished=bool(re.search(r"未识别完|没识别完|未完成|没完成|未处理完|没处理完",remainder))
    # Remove known conversational wrappers only; preserve actual names and ambiguous terms.
    hint=re.sub(r"^(?:请|帮我|麻烦|把|之前的|前边那个|前面那个|之前那个|以前的|那个|这份|这本|上次的|上次|刚才的|继续|接着|重新|再次|再|识别|处理|从|给我|的|\s)+","",remainder)
    hint=re.sub(r"(?:未识别完|没识别完|未完成|没完成|未处理完|没处理完)的?","",hint)
    hint=re.sub(r"(?:继续|接着|重新|识别|处理|开始|再|一下|的|[，。！？、,:;!?\s])+$","",hint).strip(" ，。！？、,:;!?《》\"“”")
    if hint in {"教材","资料","文件","pdf","pdf文件","之前","以前","那个教材","那个文件","那个资料","前边","前面"}:hint=""
    return {"start":start,"count":count,"hint":hint,"unfinished":unfinished}

def matching_names(files,instruction,hint):
    q=normalize(instruction);hint=normalize(hint)
    full=[f for f in files if normalize(f.name) in q]
    if full:return full
    stems=[f for f in files if len(normalize(Path(f.name).stem))>=2 and normalize(Path(f.name).stem) in q]
    if stems:return stems
    return [f for f in files if hint and hint in normalize(Path(f.name).stem)]

def propose_range(request,batches,total,next_unit):
    start=request["start"];count=request["count"]
    if start is not None:
        end=start+count-1
        for b in batches:
            if b.start<=start and end<=b.end:
                return {"start":b.start,"end":b.end,"batch_id":b.id,"note":"该范围已属于已有批次，打开原记录，不重复识别。"}
        if any(b.start<=end and start<=b.end for b in batches):
            return {"start":start,"end":end,"blocked":True,"note":"与已有批次部分重叠，请调整范围或打开原记录。"}
    pending=next((b for b in batches if b.verified_text is None),None)
    if pending:return {"start":pending.start,"end":pending.end,"batch_id":pending.id,"note":"已有未核对批次，请先核对完成。"}
    if start is None:
        start=next_unit
        end=min(start+count-1,total if total is not None else 10000,*(b.start-1 for b in batches if b.start>start))
    if start>end or end>10000 or total is not None and end>total:
        return {"start":start,"end":end,"blocked":True,"note":"已无可识别页面或范围超出文件页数。"}
    return {"start":start,"end":end,"note":"已按剩余连续页面缩小本批范围。" if end-start+1<count else "确认范围后才开始识别。"}
