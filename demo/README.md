# EmoTree On-Policy Interactive Demo v0.1

本 Demo 按 EmoTree_OnPolicy_State_Transition_Demo.md 实现。真人在网页中扮演学生林砚；环境扮演导师高启明。学生的开放文本会被解释为结构化社会行动，确定性地修改隐藏情绪、关系、动机和风险变量，并触发可观察的离散状态变化。

## 启动

    cd /root/autodl-tmp/emotree
    python demo/server.py

打开：

- Participant View: http://127.0.0.1:8000/
- Researcher Debug: http://127.0.0.1:8000/researcher.html
- Trajectory Replay: http://127.0.0.1:8000/replay.html
- World 1 状态转换图: http://127.0.0.1:8000/assets/world1-state-transition.svg

服务只使用 Python 标准库。前端无构建步骤、无第三方依赖。

## 闭环

    Student open-text action
      -> Action Interpreter
      -> impact levels
      -> fixed delta mapping
      -> trait modifiers
      -> latent state update
      -> threshold + priority + hysteresis
      -> discrete state transition
      -> observable cue
      -> state-conditioned advisor response
      -> memory update
      -> trajectory log

## 已实现的 v0.1 范围

- 1 个导师—学生署名冲突 World；
- 固定 Advisor Persona、traits、公开目标和隐藏意图；
- 15 个 0–100 latent variables；
- 7 个离散 states；
- 12 类可多标签 Student Action taxonomy；
- assertiveness、hostility、respectfulness、threat、cooperativeness、evidence orientation 六个连续维度；
- 固定 strong/moderate/mild/similar 数值映射；
- face sensitivity、dominance、risk aversion、procedural fairness、empathy trait modifiers；
- state priority 和 hysteresis；
- 可逆状态变化，State Transition 不等于 Ending；
- Text observable cue；
- 同一 cue 对应的 Talking Head control JSON 占位；
- 状态条件化导师回复；
- recent dialogue、important events、beliefs 三类 memory；
- 10–20 轮会话，当前上限 20；
- Participant / Researcher / Replay 三个视图；
- 完整 trajectory 持久化与任意轮次 fork。

## 信息隔离

Participant API 和页面只包含：

- 对话历史；
- observable text cue；
- 导师自然语言回复；
- 当前轮数。

它不会返回 latent values、State 名称、threshold、traits、hidden intentions 或 internal research log。

Researcher View 才能查看隐藏数据。当前属于研究 Demo，不是带权限认证的公开生产服务；如部署到公网，应在反向代理或服务层增加身份认证。

## 数据位置

- Scenario: demo/onpolicy/scenario.json
- Engine: demo/onpolicy/engine.py
- Session API: demo/server.py
- Trajectories: demo/data/trajectories/{session_id}.json
- Tests: demo/tests/test_onpolicy.py

每一轮保存 student text、结构化 action、state before/after、影响等级、固定 base delta、trait modifier、实际 delta、候选 state、触发条件、cue、导师回复、internal log 和 memory。

## 当前明确不做

文档将以下内容定义为后续阶段，因此 v0.1 没有伪装实现：

- Talking Head 视频生成；目前只生成文本 cue 和结构化视频控制；
- 自动 RL policy 训练；
- 多导师、多 World 同时互动；
- 自动被评估 LLM；目前由真人输入，API 结构已为替换 Human Student 留出接口；
- 未经验证的综合社会智能分数。

## 测试

    python -m unittest discover -s demo/tests -v

测试覆盖 Action Sensitivity、低敌意程序升级、History Sensitivity、负面状态恢复、多标签动作解释、15 个变量边界和 trajectory 字段完整性。
