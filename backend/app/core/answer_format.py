"""Shared generation contract. Presentation labels are not stored as mathematical content."""
ANSWER_FORMAT = r"""
【全局答案与解析格式】
只将最终结果写入 answer；不得添加“答案：”“【答案】”等字段标题，也不得重复推导。选择题使用正确选项字母，填空题按空位顺序，证明题答案可为“见解析”。对原文已有答案和解析仅做排版规范化，不修改数学内容。
solution 或 question_data.methods.body 写完整、严谨、适合考试卷面的解答。计算题以“解：”开始，证明题以“证明：”开始；写明必要条件、定理、公式及推导，不跳关键步骤。判断题给出证明或反例。不要另设思路、易错点、总结、教学口播等模块。
短式使用行内 $...$，长式使用独立 $$...$$；多行推导用 aligned 环境对齐等号、不等号。使用规范分数、极限下标、积分上下限、矩阵及分段函数。JSON 中反斜线必须正确转义。
多小问题每个小问各自保存答案和解法，不添加公共答案解析；多个空位对应独立答案。仅在确有教学价值的不同解法时提供多解，methods 中使用简短方法名称 name、正文 body、recommended 布尔值，非空方法恰好一项为推荐，不重复“方法一”等标题。单一方法不需要编号。原文没有且不能可靠求解的部分留空，不编造。
"""

def answer_format_prompt():
    return "\n"+ANSWER_FORMAT.strip()
