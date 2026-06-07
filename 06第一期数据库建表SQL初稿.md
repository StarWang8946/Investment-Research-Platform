# 第一期数据库建表 SQL 初稿

> 对应设计文档：
> [04第一期数据库表结构设计](./04第一期数据库表结构设计.md)

> 对应 SQL 文件：
> [06第一期数据库建表SQL初稿.sql](./06第一期数据库建表SQL初稿.sql)

---

## 1. 说明

这份 SQL 初稿严格按 [04第一期数据库表结构设计](./04第一期数据库表结构设计.md) 的表设计落地，目标是：

- 先提供一版可直接建库的初始 DDL
- 让第一期后端开发能立刻开始联调
- 后续再迁移到 Alembic 或其他迁移工具

---

## 2. 包含内容

当前 SQL 包含以下内容：

- PostgreSQL 扩展初始化
  - `uuid-ossp`
  - `vector`
  - `pg_trgm`
- 15 张核心表
  - `users`
  - `company_basic_info`
  - `documents`
  - `document_chunks`
  - `tags`
  - `document_tags`
  - `tasks`
  - `task_runs`
  - `research_assets`
  - `asset_revisions`
  - `asset_sources`
  - `research_asset_tags`
  - `citations`
  - `prompt_templates`
  - `system_configs`
- 主键、外键、唯一约束
- 第一批必要索引
- 向量索引
- trigram 模糊检索索引
- `tasks.callback_url` / `tasks.request_id`
- `document_chunks.embedding_model`

---

## 3. 为什么先用原生 SQL

第一期建议先有一版清晰 SQL，而不是只写 ORM 模型，原因如下：

- 表结构讨论时，SQL 比 ORM 更直观
- 方便先手工建库验证
- 方便后续再转成 Alembic migration
- 一期还在快速迭代，先把数据库边界钉住更重要

---

## 4. 使用建议

### 4.1 本地初始化顺序

1. 创建数据库
2. 执行 `06第一期数据库建表SQL初稿.sql`
3. 插入一个测试用户
4. 用后端连库做基本 CRUD 验证

### 4.2 向量维度说明

当前 `document_chunks.embedding` 使用：

```sql
vector(1024)
```

原因：

- 这版先按中等维度模型预留
- 方便一期先跑通

如果后续你选的 embedding 模型不是 1024 维，需要同步修改：

- `document_chunks.embedding`
- 向量索引
- 后端 embedding schema

同时 SQL 已增加：

```sql
embedding_model VARCHAR(128)
```

用途：

- 记录每个 chunk 使用的 embedding 模型
- 支持后续按模型重新生成向量
- 避免只看向量字段时无法判断维度和模型来源

### 4.3 去重约束说明

SQL 采用以下策略：

- `documents.source_id` 保持唯一，是文档主去重键
- `documents.checksum` 建普通索引，用于重复上传检测
- 不再使用 `(checksum, source_id)` 组合唯一，避免两个字段承担重复的唯一约束语义

### 4.4 request_id 与异步回调

SQL 已在 `tasks` 表预留：

- `request_id`
- `callback_url`

接口层约定：

- 请求 Header 使用 `X-Request-ID`
- 错误响应中的 `request_id` 与 Header 保持一致
- `callback_url` 第一期可先只保存，后续再实现 Webhook 回调

---

## 5. v2 重点优化

相较于上一版，v2 主要新增：

- `company_basic_info` 公司主数据
- `tags` / `document_tags` / `research_asset_tags`
- `research_assets.parent_asset_id` / `root_asset_id`
- `asset_revisions` 修订历史表
- `document_chunks` 结构化元数据字段
- `tasks.output_payload` / `result_summary`
- `pg_trgm` 与更多组合索引
- `tasks.callback_url` / `request_id`
- `document_chunks.embedding_model`

---

## 6. 当前 SQL 的取舍

### 已包含

- 可直接运行的基础表结构
- 可用于第一期主流程的索引
- 可兼容任务、引用、研究资产沉淀
- 可兼容标签检索和公司主数据管理
- 可兼容 API v2 中的任务状态追踪、Prompt 模板、系统配置、统计查询

### 暂未包含

- 复杂触发器
- 审计表
- 全量字段注释
- GIN 全文检索索引
- 更细粒度 CHECK 约束
- Webhook 回调触发器
- 复杂审计表

原因：

- 第一阶段优先保证可落地、可联调
- 不先把数据库做得过重

---

## 7. 下一步建议

这份 SQL 跑通后，建议下一步做四件事：

1. 生成 `seed` 初始数据脚本
2. 生成 Alembic 首版迁移
3. 让后端 ORM 模型与 SQL 对齐
4. 按 P0/P2 索引优先级拆分迁移脚本

如果你继续往下做，最自然的下一步就是：

- `07第一期初始化测试数据.sql`
- 或 `Alembic 首版 migration 初稿`
