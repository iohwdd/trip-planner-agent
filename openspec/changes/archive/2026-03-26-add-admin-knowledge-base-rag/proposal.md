## 为什么

当前产品已经将“智能助手”和“工作台”职责拆开，但智能助手仍然只能依赖通用模型知识回答，缺少可由业务侧维护的私有知识源。随着产品开始承载更明确的运营内容和内部资料，需要一个仅管理员可维护、仅增强智能助手问答的知识库模块，并为后续更稳定的 RAG 能力打下基础。

## 变更内容

- 新增一个仅管理员可见和可访问的知识库模块，作为壳层导航中的一级入口。
- 新增知识库文档管理能力，支持管理员上传、查看、删除和重建 `md` / `txt` 文档索引。
- 新增基于 `LangChain + ChromaDB + text2vec-base-chinese + cross-encoder reranker` 的 RAG 检索链路，用于增强智能助手回复。
- 将知识库原始文件保存到 MinIO，对象元数据保存到 Django/MySQL，向量索引持久化到 ChromaDB。
- 修改统一身份摘要能力，使前端能够根据 `is_staff` 判断是否展示知识库入口。
- 修改智能助手回复链路，使其在知识库可用时优先使用检索到的上下文生成答案，但不在前端展示来源引用。

## 功能 (Capabilities)

### 新增功能
- `admin-knowledge-base-management`: 提供管理员专用的知识库入口、文档管理、索引构建与状态查看能力。

### 修改功能
- `assistant-chat-experience`: 智能助手回复将接入知识库检索增强，但仍保持独立问答入口和现有会话模型。
- `identity-summary-surface`: 统一身份摘要需要暴露管理员能力开关，以驱动导航与管理员页面可见性。

## 影响

- 后端代码：`planner/models.py`、`planner/api/views.py`、`planner/api/urls.py`、`planner/services/*`、`planner/integrations/qwen.py`
- 前端代码：`frotend/src/App.vue`、`frotend/src/router.js`、`frotend/src/lib/api.js`、`frotend/src/composables/useAuth.js`、新增知识库页面与相关样式
- 基础设施与依赖：新增 `chromadb`、对象存储客户端、文本向量与重排模型依赖；增加 MinIO 配置与 ChromaDB 持久化目录配置
- 数据与存储：新增知识库与知识文档元数据表、MinIO 对象存储路径、ChromaDB 集合持久化目录
