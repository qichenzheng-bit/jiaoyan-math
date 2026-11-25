"""数学学科常量与题目「一题多解 / ※推荐方法」解析与合并工具。

约定：
1. 题库支持五大学科：高等数学、线性代数、概率论与数理统计、数学分析、高等代数。
2. 当一道题拥有多种解法时，Markdown 中使用如下标题分段（顺序支持方法一..方法十+）：
   `### ※ 方法一`（推荐解法带 `※` 前缀）与 `### 方法二`、`### 方法三` 等。
3. 只有一种解法时保持纯正文，避免破坏既有单解展示；出现 >=2 种解法时统一输出分段标题，
   便于：
   - 视频生成阶段（`recommended_solution`）只抽取带 `※` 的推荐解法制作讲解视频；
   - 后续「带答案导出 PDF」导出全部方法。
"""
from __future__ import annotations

import re

MATH_SUBJECTS: tuple[str, ...] = (
    "高等数学",
    "线性代数",
    "概率论与数理统计",
    "数学分析",
    "高等代数",
)

_SUBJECT_ALIASES: dict[str, str] = {
    "高数": "高等数学",
    "微积分": "高等数学",
    "高等数学": "高等数学",
    "线代": "线性代数",
    "线性代数": "线性代数",
    "概率": "概率论与数理统计",
    "概率论": "概率论与数理统计",
    "概率统计": "概率论与数理统计",
    "概率论与数理统计": "概率论与数理统计",
    "数分": "数学分析",
    "数学分析": "数学分析",
    "高代": "高等代数",
    "高等代数": "高等代数",
}

_CN_NUMS = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
            "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十")

_METHOD_HEAD_RE = re.compile(
    r"^\s*(?:#{1,4}\s*)?(?:\*\*)?\s*(?P<star>※\s*)?(?:【\s*(?P<star_in>※\s*)?)?"
    r"(?P<label>(?:解法|方法|思路)\s*[一二三四五六七八九十\d]+)"
    r"(?:\s*[：:】])?\s*(?:\*\*)?(?P<tail>.*)$"
)


def normalize_subject(raw: str | None) -> str:
    """把学科名称规整到五大学科之一；未知值原样裁剪保留。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    return _SUBJECT_ALIASES.get(text, text[:20])


_BLOCK_DOLLAR_RE = re.compile(r"[ \t]*\n?\$\$\s*([\s\S]*?)\s*\$\$[ \t]*\n?")
_BLOCK_BRACKET_RE = re.compile(r"[ \t]*\n?\\\[\s*([\s\S]*?)\s*\\\][ \t]*\n?")
_INLINE_MATH_SPAN_RE = re.compile(r"\$([^$\n]+?)\$")
_LIMITS_OP_RE = re.compile(r"\\(lim|sum)(?![A-Za-z])(?!\s*\\limits)\s*(?=[_^])")
_PLAIN_MATH_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_\\$])"
    r"(?:"
    r"\([A-D]\)"
    r"|\([1-9]\d?\)"
    r"|(?:[A-Za-z][A-Za-z0-9_']*(?:\([^()\n$]{1,24}\))?|-?\d+(?:\.\d+)?)"
    r"(?:[+\-*/=<>^_](?:-?\d+(?:\.\d+)?|[A-Za-z][A-Za-z0-9_']*(?:\([^()\n$]{1,24}\))?|[(){}^]+))*"
    r")"
    r"(?![A-Za-z0-9_$])"
)


def _match_delim_backward(text: str, close_idx: int, open_ch: str, close_ch: str) -> int:
    depth = 0
    for i in range(close_idx, -1, -1):
        ch = text[i]
        if ch == close_ch:
            depth += 1
        elif ch == open_ch:
            depth -= 1
            if depth == 0:
                return i
    return -1


def _match_delim_forward(text: str, open_idx: int, open_ch: str, close_ch: str) -> int:
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
    return -1


def _scan_frac_numerator(s: str, slash_idx: int) -> tuple[int, str, bool]:
    """从 `/` 向左扫描分子范围，返回 (起始下标, 分子文本, 是否去掉了外层纯分组括号)。"""
    j = slash_idx - 1
    while j >= 0 and s[j] in " \t":
        j -= 1
    if j < 0:
        return -1, "", False

    # 跳过末尾空白后的脚本附着（如 e_{n+1}、x^2、(x+1)^2）
    end_idx = j + 1
    pos = j

    def _consume_atom_left(p: int) -> tuple[int, bool]:
        """向左消费一个完整原子或带脚本原子，返回 (新左边界下标, 是否本身是可去外括号分组)。"""
        if p < 0:
            return -1, False
        # 1. 右括号 (...) / \right)
        if s[p] == ")":
            op = _match_delim_backward(s, p, "(", ")")
            if op < 0:
                return -1, False
            prefix_start = op
            # 检查 \left(
            left_part = s[:op]
            m_left = re.search(r"\\left\s*$", left_part)
            has_left = bool(m_left)
            if m_left:
                prefix_start = m_left.start()
            # 检查函数名前缀（如 \ln(...)、f(...)、\sin(...)）
            pre = s[:prefix_start]
            m_fn = re.search(r"(?:\\[A-Za-z]+|[A-Za-z](?:_[A-Za-z0-9]|_\{[^}]+\})?)\s*$", pre)
            if m_fn and m_fn.group(0).strip() not in ("\\left",):
                return m_fn.start(), False
            return prefix_start, (not has_left)

        # 2. 右花括号 {...}（如 \sqrt{...}、\mathrm{d}x、e_{n+1}、\frac{a}{b}）
        if s[p] == "}":
            ob = _match_delim_backward(s, p, "{", "}")
            if ob < 0:
                return -1, False
            cur = ob
            # 若是 \frac{A}{B} 或 _{...} / ^{...}，继续向前吸收基体与命令
            while cur > 0:
                # 吸收可选 [...]（例如 \sqrt[3]{x}）
                k = cur - 1
                while k >= 0 and s[k] in " \t":
                    k -= 1
                if k >= 0 and s[k] == "]":
                    obr = _match_delim_backward(s, k, "[", "]")
                    if obr >= 0:
                        cur = obr
                        k = cur - 1
                m_cmd = re.search(r"\\[A-Za-z]+$", s[:cur])
                if m_cmd:
                    cmd = m_cmd.group(0)
                    cur = m_cmd.start()
                    # \frac{A}{B} 需要再往前吃一个 {A}？上面 ob 吃的是 {B}，再吃前一个 {A}
                    if cmd in ("\\frac", "\\dfrac", "\\tfrac") and cur >= 0:
                        continue
                    # \mathrm{d}x 的情况不在这里，{...} 后面已经直接跟了 x，下面主循环会处理
                    break
                if cur > 0 and s[cur - 1] in "_^":
                    cur -= 1
                    sub_start, _ = _consume_atom_left(cur - 1)
                    if sub_start >= 0:
                        cur = sub_start
                    break
                if cur > 0 and s[cur - 1] == "}":
                    # 连续花括号如 \frac{a}{b} 的第一组
                    ob2 = _match_delim_backward(s, cur - 1, "{", "}")
                    if ob2 >= 0:
                        cur = ob2
                        continue
                break
            return cur, False

        # 3. 普通字母/数字/TeX 命令原子（含前导系数字母，如 2\pi、\partial z、dx、2026x、x_n）
        p0 = p
        # 若末尾是字母/数字且前面紧挨着 _ 或 ^（如 e_n、x^2）
        while p0 >= 0 and (s[p0].isalnum() or s[p0] in "._'"):
            p0 -= 1
        # 检查是否是 \cmd（如 \pi、\theta）
        if p0 >= 0 and s[p0] == "\\":
            start = p0
            # 可能带有前缀数字系数如 2\pi
            k = start - 1
            while k >= 0 and (s[k].isdigit() or s[k] == "."):
                k -= 1
            if k < start - 1:
                start = k + 1
            return start, False
        atom_start = p0 + 1
        if atom_start > p:
            return -1, False
        # 如果前面是 _ 或 ^，连带基体一起吞掉（如 e_n、x^2、\sin^2）
        if atom_start > 0 and s[atom_start - 1] in "_^":
            base_start, _ = _consume_atom_left(atom_start - 2)
            if base_start >= 0:
                return base_start, False
        # 特殊常见微积分分子连写：\partial z、\mathrm{d}x
        pre = s[:atom_start]
        m_diff = re.search(r"(?:\\partial|\\mathrm\{d\}|\\operatorname\{d\})\s*$", pre)
        if m_diff:
            return m_diff.start(), False
        # 系数 + TeX 命令，如 2\pi x
        m_coeff = re.search(r"(?:\d+(?:\.\d+)?)?\s*\\[A-Za-z]+\s*$", pre)
        if m_coeff and re.match(r"^[A-Za-z]+$", s[atom_start:p + 1]):
            return m_coeff.start(), False
        return atom_start, False

    start_idx, is_bare_paren = _consume_atom_left(pos)
    if start_idx < 0 or start_idx >= end_idx:
        return -1, "", False
    # 若本身是 e_{n+1} 这类带花括号后缀（如 \mathrm{d}x 中的 d 被花括号包裹），向后再看看是否还有紧邻变量
    raw_num = s[start_idx:end_idx].strip()
    if is_bare_paren and raw_num.startswith("(") and raw_num.endswith(")"):
        return start_idx, raw_num[1:-1].strip(), True
    return start_idx, raw_num, False


def _scan_frac_denominator(s: str, slash_idx: int) -> tuple[int, str]:
    """从 `/` 向右扫描分母范围，返回 (结束下标, 分母文本)。"""
    n = len(s)
    k = slash_idx + 1
    while k < n and s[k] in " \t":
        k += 1
    if k >= n:
        return -1, ""

    def _consume_atom_right(p: int) -> tuple[int, bool]:
        if p >= n:
            return -1, False
        # \left(...)
        m_left = re.match(r"\\left\s*\(", s[p:])
        if m_left:
            close_p = _match_delim_forward(s, p + len(m_left.group(0)) - 1, "(", ")")
            if close_p < 0:
                return -1, False
            end = close_p + 1
            m_right = re.match(r"\s*\\right\)", s[close_p:])
            if m_right and s[close_p] == ")":
                pass
            return end, False
        # 普通 (...)
        if s[p] == "(":
            close_p = _match_delim_forward(s, p, "(", ")")
            if close_p < 0:
                return -1, False
            end = close_p + 1
            if end < n and s[end] in "_^":
                end2 = _consume_script_right(end)
                return end2, False
            return end, True
        # {...}
        if s[p] == "{":
            cb = _match_delim_forward(s, p, "{", "}")
            return (cb + 1, False) if cb >= 0 else (-1, False)
        # \partial z / \mathrm{d}x
        m_diff = re.match(r"(?:\\partial|\\mathrm\{d\}|\\operatorname\{d\})\s*(?:\{[^}]+\}|[A-Za-z])", s[p:])
        if m_diff:
            end = p + m_diff.end()
            if end < n and s[end] in "_^":
                end = _consume_script_right(end)
            return end, False
        # \cmd（如 \sqrt{...}, \sqrt6, \pi, \ln(1+x), \sin x）
        m_cmd = re.match(r"\\[A-Za-z]+", s[p:])
        if m_cmd:
            end = p + m_cmd.end()
            # 可选 [opt]
            if end < n and s[end] == "[":
                cbr = _match_delim_forward(s, end, "[", "]")
                if cbr >= 0:
                    end = cbr + 1
            # 吸收参数组 {arg} 或 \sqrt6 这类单字符参数
            while end < n and s[end] == "{":
                cb = _match_delim_forward(s, end, "{", "}")
                if cb < 0:
                    break
                end = cb + 1
            if m_cmd.group(0) == "\\sqrt" and end == p + m_cmd.end() and end < n and s[end].isalnum():
                end += 1
            if end < n and s[end] in "_^":
                end = _consume_script_right(end)
            if end < n and s[end] == "(":
                cp = _match_delim_forward(s, end, "(", ")")
                if cp >= 0:
                    end = cp + 1
            return end, False
        # 数字 / 变量 / f(x) / x_n / 2\pi
        m_tok = re.match(r"(?:\d+(?:\.\d+)?(?:[A-Za-z]|\\[A-Za-z]+)?|[A-Za-z][A-Za-z0-9']*)", s[p:])
        if not m_tok:
            return -1, False
        end = p + m_tok.end()
        if end < n and s[end] in "_^":
            end = _consume_script_right(end)
        if end < n and s[end] == "(":
            cp = _match_delim_forward(s, end, "(", ")")
            if cp >= 0:
                end = cp + 1
        return end, False

    def _consume_script_right(p: int) -> int:
        cur = p
        while cur < n and s[cur] in "_^":
            cur += 1
            if cur >= n:
                break
            if s[cur] == "{":
                cb = _match_delim_forward(s, cur, "{", "}")
                if cb < 0:
                    break
                cur = cb + 1
            else:
                cur += 1
        return cur

    end_idx, is_bare_paren = _consume_atom_right(k)
    if end_idx <= k:
        return -1, ""
    raw_den = s[k:end_idx].strip()
    if is_bare_paren and raw_den.startswith("(") and raw_den.endswith(")"):
        return end_idx, raw_den[1:-1].strip()
    return end_idx, raw_den


def _convert_slash_fractions_in_math(inner: str) -> str:
    """将 `$...$` 公式体内的 `a/b`、`\\pi/2`、`\\sqrt{\\pi/2}` 等斜杠分式规范转为 `\\frac{...}{...}`。"""
    if "/" not in inner:
        return inner
    # 保护 \text{...} / \mbox{...} 内容不被改写
    saved_texts: list[str] = []

    def _mask_text_macros(src: str) -> str:
        out: list[str] = []
        i = 0
        n = len(src)
        while i < n:
            m = re.match(r"\\(?:text|mbox|url)\s*\{", src[i:])
            if m:
                ob = i + m.end() - 1
                cb = _match_delim_forward(src, ob, "{", "}")
                if cb >= 0:
                    token = f"@@TEXTSEG{len(saved_texts)}@@"
                    saved_texts.append(src[i:cb + 1])
                    out.append(token)
                    i = cb + 1
                    continue
            out.append(src[i])
            i += 1
        return "".join(out)

    cur = _mask_text_macros(inner)
    for _ in range(24):
        changed = False
        idx = 0
        while idx < len(cur):
            ch = cur[idx]
            if ch != "/":
                idx += 1
                continue
            # 跳过转义 `\/`、双斜杠 `//`、或 `\big/` `\Big/` 等显式定界符斜杠
            if idx > 0 and cur[idx - 1] in ("\\", "/"):
                idx += 1
                continue
            if idx + 1 < len(cur) and cur[idx + 1] == "/":
                idx += 2
                continue
            num_start, num, _ = _scan_frac_numerator(cur, idx)
            den_end, den = _scan_frac_denominator(cur, idx)
            if num_start >= 0 and den_end > idx and num and den:
                cur = cur[:num_start] + f"\\frac{{{num}}}{{{den}}}" + cur[den_end:]
                changed = True
                break
            idx += 1
        if not changed:
            break
    for t_i, raw_seg in enumerate(saved_texts):
        cur = cur.replace(f"@@TEXTSEG{t_i}@@", raw_seg)
    return cur


def _normalize_tex_body(inner: str, *, convert_fractions: bool = False) -> str:
    """内部公式体规范化：保证 \\lim 下标与 \\sum 上下标默认位于正上下方（\\limits），可选斜杠分式转 \\frac。"""
    body = _LIMITS_OP_RE.sub(r"\\\1\\limits", inner)
    if convert_fractions:
        body = _convert_slash_fractions_in_math(body)
    return body


#: 选项行前缀：`(A)`、`（A）`、`A.`、`A．`、`(1)` …
_OPTION_LABEL_RE = re.compile(
    r"^[ \t]*(?:[（(][ \t]*[A-Da-d1-9][ \t]*[)）]|[A-Da-d1-9][ \t]*[.．、])[ \t]*")
_TEX_CMD_START_RE = re.compile(r"\\[A-Za-z]+|\\begin\{")


def _balance_dollar_lines(text: str) -> str:
    """补齐丢失的 `$`：模型偶尔把选项写成 `(A) g(0)=1$`（丢了开头的 `$`）。

    不配对时逐行补：优先补在选项标记之后（`(A) $…$`），否则补在该行第一个
    TeX 命令之前；仍不配对（多为标题被截断的 `$…` 残片）就整段丢弃。
    这样「乱码」只会退化成少一段公式，不会把后面的正文整段吞进公式里。
    """
    if "$" not in text:
        return text
    lines: list[str] = []
    for line in text.split("\n"):
        if line.count("$") % 2 == 0:
            lines.append(line)
            continue
        fixed = None
        if line.count("$") == 1:
            first = line.index("$")
            label = _OPTION_LABEL_RE.match(line)
            if label and label.end() < first:
                fixed = line[:label.end()] + "$" + line[label.end():]
            else:
                hit = _TEX_CMD_START_RE.search(line[:first])
                if hit and hit.start() < first:
                    fixed = line[:hit.start()] + "$" + line[hit.start():]
        else:
            cut = line.rfind("$")
            head = line[:cut].rstrip() if cut >= 0 else ""
            if head and head.count("$") % 2 == 0:
                fixed = head
        lines.append(line if fixed is None else fixed)
    return "\n".join(lines)


def _wrap_plain_math_segment(segment: str) -> str:
    """在纯文本片段中把选择题字母 (A)-(D)、英文字母、算式与数字包成单 `$...$`。"""
    if not segment:
        return segment
    lines = segment.split("\n")
    out_lines: list[str] = []
    for line in lines:
        # 保留多解法标题行（如 `### ※ 方法一`）不被包裹
        if re.match(r"^\s*#{1,4}\s*", line):
            out_lines.append(line)
            continue
        out_lines.append(_PLAIN_MATH_TOKEN_RE.sub(lambda m: f"${m.group(0)}$", line))
    return "\n".join(out_lines)


def normalize_latex_delimiters(text: str | None, *, convert_fractions: bool = False) -> str:
    """规整定界符为紧凑单 `$...$`、\\lim 下标正下方，并将裸字母/选项/数字纳入 LaTeX 渲染。"""
    src = str(text or "").replace("\r\n", "\n")
    if not src:
        return ""
    src = _balance_dollar_lines(src)

    def _to_single(m: re.Match) -> str:
        inner = re.sub(r"\s*\n+\s*", " ", m.group(1)).strip()
        if not inner:
            return ""
        lead = "\n" if m.group(0).lstrip(" \t").startswith("\n") else ""
        trail = "\n" if m.group(0).rstrip(" \t").endswith("\n") else ""
        return f"{lead}${inner}${trail}"

    out = _BLOCK_DOLLAR_RE.sub(_to_single, src)
    out = _BLOCK_BRACKET_RE.sub(_to_single, out)
    out = re.sub(r"\n{2,}", "\n", out)

    # 逐段扫描 `$...$`：公式内部加 \lim\limits_（及可选斜杠分式转 \frac），公式外裸字母/选项/数字加 $...$
    parts: list[str] = []
    pos = 0
    for m in _INLINE_MATH_SPAN_RE.finditer(out):
        if m.start() > pos:
            parts.append(_wrap_plain_math_segment(out[pos:m.start()]))
        inner = _normalize_tex_body(m.group(1), convert_fractions=convert_fractions)
        parts.append(f"${inner}$")
        pos = m.end()
    if pos < len(out):
        parts.append(_wrap_plain_math_segment(out[pos:]))
    return "".join(parts).strip()


def normalize_slash_fractions(text: str | None) -> str:
    """把文本中所有数学公式内的斜杠分式统一转为 `\\frac{...}{...}`。"""
    return normalize_latex_delimiters(text, convert_fractions=True)


def method_label(index: int) -> str:
    """1-based 序号转中文方法名（方法一、方法二…）。"""
    idx = max(1, int(index))
    if idx <= len(_CN_NUMS):
        return f"方法{_CN_NUMS[idx - 1]}"
    return f"方法{idx}"


def _norm_compare(text: str) -> str:
    return re.sub(r"[\s`*_~【】：:，。,.；;()（）]+", "", str(text or "")).lower()


def parse_methods(solution_text: str | None) -> list[dict]:
    """把 `reference_solution` 文本拆成有序方法列表 `[{index,label,recommended,body}]`。"""
    text = str(solution_text or "").replace("\r\n", "\n").strip()
    if not text or text == "待补充解析":
        return []
    lines = text.split("\n")
    blocks: list[dict] = []
    cur: dict | None = None
    preamble: list[str] = []

    for line in lines:
        m = _METHOD_HEAD_RE.match(line)
        if m:
            if cur is not None:
                cur["body"] = "\n".join(cur["lines"]).strip()
                blocks.append(cur)
            star = bool((m.group("star") or "").strip() or (m.group("star_in") or "").strip())
            tail = (m.group("tail") or "").lstrip("：: 】\t")
            cur = {
                "recommended": star,
                "lines": [tail] if tail else [],
            }
            continue
        if cur is not None:
            cur["lines"].append(line)
        else:
            preamble.append(line)

    if cur is not None:
        cur["body"] = "\n".join(cur["lines"]).strip()
        blocks.append(cur)

    if not blocks:
        return [{
            "index": 1,
            "label": method_label(1),
            "recommended": True,
            "body": text,
        }]

    pre_text = "\n".join(preamble).strip()
    if pre_text:
        blocks.insert(0, {"recommended": False, "body": pre_text})

    cleaned: list[dict] = []
    has_star = any(b.get("recommended") for b in blocks)
    for idx, item in enumerate(blocks, start=1):
        body = str(item.get("body") or "").strip()
        if not body:
            continue
        rec = bool(item.get("recommended")) if has_star else (idx == 1)
        cleaned.append({
            "index": len(cleaned) + 1,
            "label": method_label(len(cleaned) + 1),
            "recommended": rec,
            "body": body,
        })
    if cleaned and not any(m["recommended"] for m in cleaned):
        cleaned[0]["recommended"] = True
    return cleaned


def format_methods(methods: list[dict], *, always_headers: bool = False) -> str:
    """把方法列表格式化为规范 Markdown。仅有一种解法时默认返回纯正文。"""
    clean = [
        {"body": str(m.get("body") or "").strip(), "recommended": bool(m.get("recommended"))}
        for m in (methods or [])
        if str(m.get("body") or "").strip()
    ]
    if not clean:
        return ""
    if len(clean) == 1 and not always_headers:
        return clean[0]["body"]

    rec_seen = False
    for m in clean:
        if m["recommended"] and not rec_seen:
            rec_seen = True
        else:
            m["recommended"] = False
    if not rec_seen:
        clean[0]["recommended"] = True

    parts: list[str] = []
    for idx, m in enumerate(clean, start=1):
        prefix = "※ " if m["recommended"] else ""
        parts.append(f"### {prefix}{method_label(idx)}\n{m['body']}")
    return "\n\n".join(parts)


def recommended_solution(solution_text: str | None) -> str:
    """抽取带 `※` 的推荐解法正文（供视频脚本生成使用）。"""
    methods = parse_methods(solution_text)
    if not methods:
        return str(solution_text or "").strip()
    for m in methods:
        if m.get("recommended"):
            return m["body"]
    return methods[0]["body"]


def alternative_method_summaries(solution_text: str | None, *, limit: int = 3) -> list[dict[str, str]]:
    """提取非推荐备选解法的名称与首句思路，供模型在思维引导中对比选型依据。"""
    methods = parse_methods(solution_text)
    if len(methods) <= 1:
        return []
    out: list[dict[str, str]] = []
    for item in methods:
        if item.get("recommended"):
            continue
        body = re.sub(r"\s+", " ", str(item.get("body") or "")).strip()
        if not body:
            continue
        out.append({
            "label": str(item.get("label") or ""),
            "preview": body[:160],
        })
        if len(out) >= limit:
            break
    return out


def merge_solutions(
    existing_text: str | None,
    incoming_text: str | None,
    *,
    decision: str = "append",
    prefer: str = "existing",
    merged_body: str = "",
    target_index: int | None = None,
) -> tuple[str, list[dict], str]:
    """合并同一题的新旧解析。

    decision:
      - ``skip``: 保持已有解析不变
      - ``merge``: 判定与某已有方法相同，替换为更清晰的版本（优先用 merged_body）
      - ``append``: 判定为新方法，若不完全重复则追加为方法二/三…，按 prefer 设置 ※
    """
    existing = parse_methods(existing_text)
    incoming_clean = recommended_solution(incoming_text) if len(parse_methods(incoming_text)) > 1 else str(incoming_text or "").strip()
    if incoming_clean == "待补充解析":
        incoming_clean = ""

    if not existing:
        if not incoming_clean:
            return "", [], "empty"
        methods = [{"index": 1, "label": method_label(1), "recommended": True, "body": incoming_clean}]
        return format_methods(methods), methods, "initialized"

    if not incoming_clean or decision == "skip":
        return format_methods(existing), existing, "kept"

    if decision == "merge":
        idx = (int(target_index) - 1) if target_index and 1 <= int(target_index) <= len(existing) else 0
        replacement = str(merged_body or "").strip()
        if not replacement:
            replacement = incoming_clean if prefer == "incoming" else (
                incoming_clean if len(incoming_clean) > len(existing[idx]["body"]) * 1.15 and prefer != "existing_strict"
                else existing[idx]["body"]
            )
        existing[idx]["body"] = replacement
        if prefer == "incoming":
            for i, m in enumerate(existing):
                m["recommended"] = (i == idx)
        return format_methods(existing), existing, "merged"

    # append new method (dedupe exact/near-identical body)
    in_norm = _norm_compare(incoming_clean)
    for m in existing:
        if _norm_compare(m["body"]) == in_norm:
            if prefer == "incoming":
                for other in existing:
                    other["recommended"] = (other is m)
            return format_methods(existing), existing, "identical_skipped"

    use_incoming_star = (prefer == "incoming")
    if use_incoming_star:
        for m in existing:
            m["recommended"] = False
    existing.append({
        "index": len(existing) + 1,
        "label": method_label(len(existing) + 1),
        "recommended": use_incoming_star or not any(m.get("recommended") for m in existing),
        "body": incoming_clean,
    })
    return format_methods(existing), existing, "appended"
