"""内容查重 · 规范化与指纹（纯函数，无数据库依赖）

为什么单独放在 core：
    * 迁移回填旧数据（core/content_dedup_migrations.py）和接口查重
      （api/content_dedup_service.py）必须使用**同一份**规则，放 core 谁都能引；
    * 纯函数便于单测逐条比对，避免再出现「Python 一套、SQL 一套」的历史问题。

规范化只做「不改变数学含义」的等价处理：
    1. NFKC：全角字母/数字/括号/标点归一（Ａ→A）（，→,）；
    2. 统一数学定界符：$$…$$、\\[…\\]、\\(…\\) 都写成 $…$；
    3. 去掉纯排版命令：\\, \\; \\: \\! \\quad \\qquad \\displaystyle
       \\textstyle \\limits \\ 以及数学里的 ~（只影响间距，不影响内容）；
    4. 去掉 \\left / \\right（只影响括号大小）；
    5. 拆分类命令统一：\\dfrac \\tfrac \\cfrac → \\frac；
    6. 同义符号统一：\\le→\\leq、\\ge→\\geq、\\ne→\\neq、\\to→\\rightarrow、
       \\gets→\\leftarrow、\\lt→<、\\gt→>；
    7. 去掉空分组 {}；
    8. 空白折叠（normalize）或整体删除（canonical，用于精确指纹）。

明确**不做**的事（避免把不同题判成同一题）：
    * 不删数字、负号、指数、括号、运算符；
    * 不把 \\cdot 当成 \\times、不把小写 x 当成大写 X（字母大小写有意义）；
    * 不做代数变形/化简，也不做数学等价性证明。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

#: 指纹算法版本：规则变化时 +1，旧指纹会被重新计算（迁移里按版本重算）
FINGERPRINT_VERSION = "v1"

_BRACKET_BLOCK = re.compile(r"\\\[(.+?)\\\]", re.S)
_PAREN_INLINE = re.compile(r"\\\((.+?)\\\)", re.S)
_DOLLAR_BLOCK = re.compile(r"\$\$(.+?)\$\$", re.S)

#: 纯排版命令：删掉不改变内容，只是间距/字号
_TYPO_COMMANDS = re.compile(
    r"\\[,;:!]|\\q?quad(?![a-zA-Z])|\\displaystyle|\\textstyle|\\limits"
    r"|\\left|\\right|\\(?=\s)|~")
_FRAC_ALIASES = re.compile(r"\\[dtc]frac(?![a-zA-Z])")
_SYMBOL_ALIASES = (
    (re.compile(r"\\leqslant(?![a-zA-Z])"), r"\\leq"),
    (re.compile(r"\\geqslant(?![a-zA-Z])"), r"\\geq"),
    (re.compile(r"\\le(?![a-zA-Z])"), r"\\leq"),
    (re.compile(r"\\ge(?![a-zA-Z])"), r"\\geq"),
    (re.compile(r"\\ne(?![a-zA-Z])"), r"\\neq"),
    (re.compile(r"\\to(?![a-zA-Z])"), r"\\rightarrow"),
    (re.compile(r"\\gets(?![a-zA-Z])"), r"\\leftarrow"),
    (re.compile(r"\\lt(?![a-zA-Z])"), "<"),
    (re.compile(r"\\gt(?![a-zA-Z])"), ">"),
)
_EMPTY_GROUP = re.compile(r"\{\}")
_HSPACE = re.compile(r"[ \t\u00a0\u3000]+")
_ANY_SPACE = re.compile(r"\s+")
_LEADING_QNO = re.compile(r"^(?:\$?\d+\$?\s*[.．、]|第\s*\d+\s*题[：:、.]?|\(\s*\d+\s*\))\s*")
_LEADING_SCORE = re.compile(r"^[（(]\s*本题满分\s*\$?\d+\$?\s*分\s*[)）]\s*")
_CLEAN_QNO_RE = re.compile(
    r"^\s*(?:"
    r"\$[ \t]*\d{1,3}[ \t]*[.．、](?!\d)[ \t]*\$"
    r"|\$[ \t]*\d{1,3}[ \t]*\$[ \t]*[.．、](?!\d)"
    r"|\d{1,3}[ \t]*[.．、](?!\d)"
    r"|第[ \t]*\d{1,3}[ \t]*题[：:、.]?"
    r")[ \t]*"
)
_CLEAN_SCORE_RE = re.compile(
    r"^\s*[（(\[][ \t]*(?:本题[ \t]*)?(?:满分[ \t]*)?\$?\d+(?:\.\d+)?\$?[ \t]*分[ \t]*[)）\]][ \t]*"
)
_CLEAN_TITLE_QNO_RE = re.compile(r"^\s*第\s*\d{1,3}\s*题\s*(?:[·•.\-：:]\s*)?")
_PAGE_CONT_NOTE = re.compile(
    r"(?:[（(\[【]\s*(?:"
    r"(?:本体|本题)?题干\s*(?:续下页|接下页|转下页|接上页|承上页|续上页)"
    r"|续下页|接下页|接上页|续上页|转下页|承上页|续前页|下页续|本页完|下页见"
    r"|(?:上接|下转)\s*第\s*\d+\s*页"
    r"|第\s*\d+\s*页\s*[，,/／]?\s*共\s*\d+\s*页"
    r")\s*[)）\]】]"
    r"|(?:本体|本题)题干\s*(?:续下页|接下页|转下页|接上页|承上页|续上页)"
    r"|(?:^|(?<=\s))(?:续下页|接下页|接上页|续上页|转下页|承上页)(?=\s|$))"
)
_TRAILING_SCORE_RE = re.compile(
    r"[（(\[][ \t]*(?:本题(?:满分)?|满分)[ \t]*\$?\d+(?:\.\d+)?\$?[ \t]*分[ \t]*[)）\]][ \t]*[。.]?[ \t]*$"
)
_EXAM_BOILERPLATE_LINE_RE = re.compile(
    r"^(?:"
    r"绝密\s*★?\s*启用前"
    r"|.*密封线内?(?:不准|不要|禁止)答题.*"
    r"|(?:扫描全能王|微信公众号|QQ群|扫码关注|微信扫码)[：:\s\S]*"
    r"|考生注意[：:].{0,180}"
    r"|[一二三四五六七八九十]+、\s*(?:选择题|填空题|解答题|计算题|证明题)[：:]\s*\d+[～~—\-]\d+\s*小题.*"
    r"|下列每[小]?题给出的四个选项中.*"
    r")$",
    re.MULTILINE,
)
_STYLE_CMDS = re.compile(r"\\(?:boldsymbol|mathbf|mathrm|mathit|bm|Bigg|bigg|Big|big)(?![a-zA-Z])")
_SINGLE_CHAR_BRACE = re.compile(r"\{([A-Za-z0-9\\]+)\}")


def clean_question_problem_text(value) -> str:
    """过滤题干开头/结尾外层题号、满分标注、页眉水印、考试须知及跨页提示，保留正文、小题号与填空横线。"""
    text = str(value or "").strip()
    if not text:
        return ""
    text = _EXAM_BOILERPLATE_LINE_RE.sub("", text)
    text = _PAGE_CONT_NOTE.sub("", text)
    text = re.sub(r"\n{3,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    for _ in range(4):
        nxt = _CLEAN_QNO_RE.sub("", text, count=1).lstrip()
        nxt = _CLEAN_SCORE_RE.sub("", nxt, count=1).lstrip()
        if nxt == text:
            break
        text = nxt
    text = _TRAILING_SCORE_RE.sub("", text).strip()
    return text


_ANS_PREFIX_RE = re.compile(r"^\s*(?:【\s*(?:参考)?答案\s*】\s*[：:]?|参考答案\s*[：:]|答案\s*[：:]|答\s*[：:])\s*")
_SOL_PREFIX_RE = re.compile(r"^\s*(?:【\s*(?:参考)?(?:解析|详解|解答)\s*】\s*[：:]?|参考解析\s*[：:]|详解\s*[：:]|解析\s*[：:])\s*")
_ANA_PREFIX_RE = re.compile(r"^\s*(?:【\s*(?:思路(?:点拨)?|考点(?:分析)?|分析)\s*】\s*[：:]?|思路点拨\s*[：:]|考点分析\s*[：:])\s*")


def clean_solution_and_answer_fields(answer: str | None, reference_solution: str | None, analysis: str | None) -> tuple[str, str, str]:
    """清理答案、解析、思路点拨开头的套话标签，并过滤无关页眉水印与分页提示。"""
    ans = _PAGE_CONT_NOTE.sub("", str(answer or "").strip())
    ans = _ANS_PREFIX_RE.sub("", ans).strip()

    sol = _EXAM_BOILERPLATE_LINE_RE.sub("", str(reference_solution or "").strip())
    sol = _PAGE_CONT_NOTE.sub("", sol).strip()
    if not sol.lstrip().startswith("###"):
        sol = _SOL_PREFIX_RE.sub("", sol).strip()

    ana = _EXAM_BOILERPLATE_LINE_RE.sub("", str(analysis or "").strip())
    ana = _PAGE_CONT_NOTE.sub("", ana).strip()
    ana = _ANA_PREFIX_RE.sub("", ana).strip()
    return ans, sol, ana


def strip_title_question_number(value) -> str:
    """去掉自动生成标题开头的「第X题 · 」，保留核心考点名称。"""
    text = str(value or "").strip()
    if not text:
        return ""
    return _CLEAN_TITLE_QNO_RE.sub("", text, count=1).strip()


def normalize_text(value) -> str:
    """安全规范化：用于展示与相似度比较（保留空白语义）。"""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _BRACKET_BLOCK.sub(lambda m: "$" + m.group(1) + "$", text)
    text = _PAREN_INLINE.sub(lambda m: "$" + m.group(1) + "$", text)
    text = _DOLLAR_BLOCK.sub(lambda m: "$" + m.group(1) + "$", text)
    text = _FRAC_ALIASES.sub(r"\\frac", text)
    for pattern, replacement in _SYMBOL_ALIASES:
        text = pattern.sub(replacement, text)
    text = _TYPO_COMMANDS.sub("", text)
    text = _EMPTY_GROUP.sub("", text)
    text = _HSPACE.sub(" ", text)
    text = _ANY_SPACE.sub(" ", text)
    return text.strip()


def problem_search_text(value) -> str:
    """用于相似题检索与跨卷对比的题干规范化：剥离题号/满分/接上页注释及纯字体粗细修饰。"""
    text = normalize_text(value)
    text = _PAGE_CONT_NOTE.sub("", text).strip()
    for _ in range(3):
        nxt = _LEADING_QNO.sub("", text).strip()
        nxt = _LEADING_SCORE.sub("", nxt).strip()
        if nxt == text:
            break
        text = nxt
    text = _STYLE_CMDS.sub("", text)
    text = _SINGLE_CHAR_BRACE.sub(r"\1", text)
    text = _ANY_SPACE.sub(" ", text).strip()
    return text


def canonical_text(value) -> str:
    """精确比对用的规范形式：在 normalize 基础上删除所有空白。

    TeX 里 `\\frac {1} {2}` 与 `\\frac{1}{2}` 等价，去掉空白不会改变含义；
    数字、符号、括号、大小写全部保留。
    """
    return _ANY_SPACE.sub("", normalize_text(value))


def _digest(canonical: str) -> str:
    return hashlib.sha256(
        (FINGERPRINT_VERSION + "\x1f" + canonical).encode("utf-8")).hexdigest()


def question_fingerprint(problem, reference_solution, answer="") -> str:
    """题目的完全重复指纹：题干 + 解析 + 答案 三者都一致才算完全重复。

    只比题干会把「同题不同解析」错判成完全重复，所以解析与答案一起进指纹；
    它们的差异由相似度分支给出「解析不同 / 答案不同」的疑似重复提示。
    """
    canonical = "\n".join((
        canonical_text(problem),
        "\x1e" + canonical_text(reference_solution),
        "\x1e" + canonical_text(answer),
    ))
    return _digest(canonical)


def unit_fingerprint(name, content) -> str:
    """知识单元的完全重复指纹：名称 + 正文都一致。"""
    canonical = canonical_text(name) + "\x1e" + canonical_text(content)
    return _digest(canonical)


def question_stem_key(problem):
    """Candidate index only, not a proof of mathematical equivalence."""
    return _digest("stem\x1e"+canonical_text(problem))
