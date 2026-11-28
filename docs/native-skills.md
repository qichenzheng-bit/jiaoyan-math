# 微光数学原生 Skills（V1）

七份 skills/<name>/SKILL.md 是业务规则源文件。独立安装 Worker 仍采用单文件部署，deploy/qoder_worker.py 的 NATIVE_SKILLS 为相同内容的内嵌副本；修改后同步两处，test_native_skill_bundle 强制校验文件及安装内容一致。

原生 Agent 使用 SDK Skill 工具按语义自主选择，不按关键词路由、不增加前端选择器。聊天只读，工作使用原工具白名单，正式审核由用户完成。视频工作 Skill 仅负责业务操作；独立视频推理的 skills=[]、tools=[] 和原教学提示词保持不变。

主应用 CI 发布不等于独立 Worker 更新。待主应用部署成功、模型队列空闲后，从可信的当前发布目录执行 sudo bash deploy/upgrade-qoder-native-agent.sh，检查 Worker 24，失败回滚。保留 CLI 登录、会话、记忆及业务数据。

验收：pytest tests/test_qoder_worker.py 检查文件、安装及注册契约；真实 SDK 合成烟测及自然语言自动调用须在已授权服务器进行。验证数学答疑、前10页资料录入、考点统计、局部排版、视频微调、普通聊天，观察 SDK 实际 Skill 调用和业务回执，不对真实数据执行写入测试。静态测试不证明真实模型自动选择效果。
