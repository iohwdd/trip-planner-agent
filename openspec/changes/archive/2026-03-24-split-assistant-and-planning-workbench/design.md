## 上下文

现有系统将对话输入和结构化表单输入都落到 `ChatSessionRecord -> ChatTurnRecord -> TripPlanOutput` 这一条链路中。前端因此只能把聊天区当成主工作台，结构化表单只是聊天的附属输入方式；后端也只能在单条工作流里同时处理普通问答与旅行规划。

这与新的产品方向冲突：
- 对话应是一个独立的智能助手，可由系统提示词约束，后续再扩展联网搜索和 RAG
- 工作台应是纯流程化、表单式的旅行规划生成入口，强调结构化输入、执行结果和方案沉淀

## 目标 / 非目标

**目标：**
- 在产品结构上明确分离 `智能助手` 与 `流程工作台`
- 在后端数据模型上分离 assistant conversations 与 structured planning runs
- 允许工作台运行结果直接保存为旅行方案
- 保留登录、游客态与资产能力，但按新域模型重新组织
- 保持现有旅行规划工作流与结果结构尽可能复用，降低重构成本

**非目标：**
- 本次不实现联网搜索、RAG 或多工具助手
- 本次不追求流式助手输出，优先实现稳定的同步助手问答闭环
- 本次不删除旧聊天规划接口，只将其降级为兼容层

## 决策

### 决策 1：新增独立的助手会话模型，而不是继续复用 `ChatSessionRecord`

采用：
- `AssistantConversationRecord`
- `AssistantMessageRecord`

原因：
- 助手域不再需要旅行规划特有字段，如 `confirmed_constraints`、`latest_result`、`active_turn_id`
- 对话助手的消息语义比规划回合更自然，后续扩展搜索/RAG 时也更贴近标准聊天模型

备选：
- 继续复用 `ChatSessionRecord`，仅靠 `assistant_mode=general` 区分
  - 否决原因：会持续污染产品语义与数据结构，无法真正完成拆分

### 决策 2：工作台继续复用现有 `PlanningJob + PlannerRun` 作为执行内核

采用：
- 保留 `/api/plans/` 与 `PlanningJob`
- 前端工作台直接发起 structured planning run
- 为 `TripPlanRecord` 增加对 `PlanningJob` 的可选引用，使其支持从 run 保存

原因：
- 现有 one-shot planning 已经天然更接近表单式工作台
- 可以避免再造一套新的规划执行内核，把重构重点放在产品切分和资产路径上

备选：
- 再新增 `WorkbenchSessionRecord`
  - 暂不采用：会引入第二套规划状态存储，增加迁移和实现复杂度

### 决策 3：助手 API 与工作台 API 分开命名空间

采用：
- `/api/assistant/conversations/...`
- `/api/plans/...` 继续承担工作台运行
- `/api/plans/<run_id>/save/` 新增从运行结果保存资产的能力

原因：
- API 层清晰表达产品边界
- 前端状态管理可以自然拆成 `useAssistant` 与 `useWorkbench`

备选：
- 继续使用 `/api/chat/...`
  - 否决原因：命名会继续暗示“聊天就是规划”

### 决策 4：前端主入口改为双产品面板

采用：
- `AssistantPage` 作为智能助手页
- `WorkbenchPage` 作为流程化规划页
- 历史页重心从“会话规划历史”转为“助手会话历史”与“方案资产”

原因：
- 用户在进入系统时就能感知这是两个不同产品能力
- 视觉和交互上不再需要解释“聊天和工作台到底是什么关系”

## 风险 / 权衡

- [风险] 旧聊天规划接口仍然存在，短期内存在双轨语义
  → 缓解：新前端完全切到新入口；文档明确旧接口为兼容层

- [风险] 从 `PlanningJob` 直接保存为 `TripPlanRecord` 后，方案来源会同时存在 `source_session` 和 `source_job`
  → 缓解：将两者都设为可选来源字段，并在前端明确展示来源类型

- [风险] 助手先用同步问答，体验上不如原有 SSE 流式顺滑
  → 缓解：本次优先完成领域拆分；后续在助手域单独补 streaming

- [风险] 现有测试大量假设首页是聊天规划工作台
  → 缓解：同步更新前端测试和后端 API 测试，只覆盖新的主链路

## Migration Plan

1. 新增助手会话/消息模型与迁移
2. 为 `TripPlanRecord` 增加 `source_job`，新增工作台结果保存接口
3. 新增助手服务与 API，保持旧聊天规划接口不删
4. 前端新增 `AssistantPage` 和 `WorkbenchPage`，主导航切换到双入口
5. 将现有首页改为助手入口，工作台改为独立结构化页面
6. 更新测试和文档

回滚策略：
- 保留旧聊天规划接口与旧表结构
- 如果新助手域出现问题，可在前端临时切回旧路由而不丢失原有规划能力

## Open Questions

- 助手历史页是否在本次同时提供，还是先把会话历史入口做最小版本
- 工作台是否需要“最近一次运行记录”列表，还是先只保留当前运行 + 已保存方案
- 助手域后续接入搜索/RAG 时，是否需要预留 tool trace 存储结构
