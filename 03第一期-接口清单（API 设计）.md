# 第一期接口清单（API 设计）

> 适用阶段：第一期“研究信息中台 MVP”
>
> 版本：v2
>
> 目标：给第一期最小多 Agent 架构提供可直接开发的接口清单，并与数据库 v2、实施文档、参考优化建议保持一致。

---

## 1. 设计原则

### 1.1 API 前缀

业务接口统一使用 `/api/v1` 前缀：

- `GET /health`
- `GET /api/v1/health`
- `GET /api/v1/system/info`
- `POST /api/v1/documents`

原因：

- 给二期、三期预留版本升级空间
- 避免未来接口变更时影响已有前端或脚本
- FastAPI 路由分组更清晰
- `GET /health` 可作为负载均衡、容器探活的短路径别名保留

### 1.2 为什么第一期采用 REST API

第一期建议以 REST API 为主，原因如下：

- 单人开发调试快
- 与 FastAPI 结合自然
- 文档、任务、资产、问答这些对象天然适合资源化设计
- 后续前端不管是 Streamlit 还是 Next.js 都容易接入

### 1.3 命名约定

- 创建资源优先使用 `POST /resources`
- 查询列表使用 `GET /resources`
- 查询详情使用 `GET /resources/{id}`
- 更新资源使用 `PUT /resources/{id}`
- 删除资源使用 `DELETE /resources/{id}`，第一期默认软删除
- 生成类能力可以保留动作型路径，例如 `/qa/ask`、`/qa/ask/stream`

说明：

- 文档上传本质是创建文档资源，因此 v2 推荐 `POST /api/v1/documents`
- 如果已经实现过旧接口，`POST /documents/upload` 可作为兼容别名保留到一期结束

### 1.4 一期 API 范围

- 系统接口
- 公司主数据接口
- 标签接口
- 文档接口
- 检索与问答接口
- 任务接口
- 研究资产接口
- 模板与配置接口
- 统计看板接口

---

## 2. 接口总览

|模块|接口数量|用途|
|---|---:|---|
|系统|3|健康检查与基础信息|
|公司主数据|3|公司列表、详情、创建|
|标签|9|标签管理、文档/资产打标签|
|文档|11|上传、列表、详情、解析、切分、预览、批量、删除、回收站|
|检索问答|5|混合检索、同步问答、流式问答、备忘录、日报|
|任务|4|创建任务、查询任务、执行记录|
|研究资产|9|保存、列表、详情、更新、版本、导出、删除|
|模板配置|4|Prompt 和系统参数|
|统计看板|4|文档、检索、资产、任务统计|

---

## 3. 通用规范

### 3.1 统一成功响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

### 3.2 统一失败响应

```json
{
  "code": 2003,
  "message": "document parse failed",
  "data": null,
  "request_id": "req_20260604_0001"
}
```

### 3.3 分页请求参数

所有列表接口统一支持：

|参数|类型|默认值|说明|
|---|---:|---:|---|
|page|int|1|页码，从 1 开始|
|page_size|int|20|每页数量，建议最大 100|
|sort_by|string|created_at|排序字段|
|sort_order|string|desc|`asc` 或 `desc`|

### 3.4 分页响应结构

```json
{
  "items": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100,
    "total_pages": 5,
    "has_next": true,
    "has_prev": false
  }
}
```

### 3.5 状态枚举

|对象|字段|枚举|
|---|---|---|
|documents|parse_status|`pending` / `processing` / `parsed` / `failed`|
|tasks|status|`pending` / `running` / `succeeded` / `failed` / `cancelled`|
|research_assets|status|`draft` / `reviewed` / `published` / `archived`|
|tags|status|`active` / `inactive`|

### 3.6 错误码

|错误码|说明|
|---:|---|
|1001|系统内部错误|
|1002|配置不存在|
|1003|外部模型服务不可用|
|2001|文档不存在|
|2002|文档类型不支持|
|2003|文档解析失败|
|2004|文档已存在|
|2005|文档未完成入库|
|3001|检索参数错误|
|3002|向量模型不可用|
|3003|检索无结果|
|3004|LLM 生成失败|
|4001|任务不存在|
|4002|任务类型不支持|
|4003|任务执行失败|
|5001|资产不存在|
|5002|资产版本冲突|
|5003|资产导出失败|
|6001|公司不存在|
|7001|标签不存在|

---

## 4. 系统接口

## 4.1 `GET /health`

### 用途

- 健康检查
- 也支持 `GET /api/v1/health`，便于所有业务接口路径保持一致

### 响应示例

```json
{
  "status": "ok",
  "service": "investment-research-platform",
  "time": "2026-06-04T16:00:00+08:00"
}
```

---

## 4.2 `GET /api/v1/system/info`

### 用途

- 返回系统版本和关键配置摘要

### 响应示例

```json
{
  "app_version": "0.1.0",
  "env": "local",
  "vector_enabled": true,
  "llm_provider": "external",
  "embedding_model": "bge-m3",
  "rerank_enabled": true
}
```

---

## 5. 公司主数据接口

数据库已设计 `company_basic_info`，公司是文档、检索、研究资产的核心锚点，因此一期需要提供最小公司主数据接口。

## 5.1 `GET /api/v1/companies`

### 用途

- 查询公司列表
- 支持前端公司选择框、检索过滤、资产归档

### 查询参数

|参数|类型|说明|
|---|---|---|
|keyword|string|公司代码、全称、简称模糊搜索|
|industry_code_l1|string|一级行业编码|
|industry_name_l1|string|一级行业名称|
|market|string|市场|
|is_active|boolean|是否有效|
|page|int|页码|
|page_size|int|每页数量|

### 响应示例

```json
{
  "items": [
    {
      "id": "company-uuid-1",
      "company_code": "600519",
      "company_name": "贵州茅台酒股份有限公司",
      "company_short_name": "贵州茅台",
      "exchange": "SSE",
      "market": "A股",
      "industry_name_l1": "食品饮料",
      "is_active": true
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

---

## 5.2 `GET /api/v1/companies/{company_code}`

### 用途

- 获取公司详情

### 响应示例

```json
{
  "id": "company-uuid-1",
  "company_code": "600519",
  "company_name": "贵州茅台酒股份有限公司",
  "company_short_name": "贵州茅台",
  "exchange": "SSE",
  "market": "A股",
  "industry_code_l1": "C15",
  "industry_name_l1": "食品饮料",
  "industry_code_l2": "C151",
  "industry_name_l2": "白酒",
  "security_type": "stock",
  "list_date": "2001-08-27",
  "is_active": true
}
```

---

## 5.3 `POST /api/v1/companies`

### 用途

- 新增公司主数据
- 一期可以只给管理脚本或管理员使用

### 请求体示例

```json
{
  "company_code": "600519",
  "company_name": "贵州茅台酒股份有限公司",
  "company_short_name": "贵州茅台",
  "exchange": "SSE",
  "market": "A股",
  "industry_name_l1": "食品饮料",
  "industry_name_l2": "白酒"
}
```

---

## 6. 标签接口

数据库已设计 `tags`、`document_tags`、`research_asset_tags`。标签用于文档分类、检索过滤、研究资产归档。

## 6.1 `GET /api/v1/tags`

### 用途

- 查询标签列表

### 查询参数

|参数|类型|说明|
|---|---|---|
|tag_type|string|标签类型，如 `company`、`industry`、`theme`、`event`|
|parent_id|string|父标签 ID|
|keyword|string|标签编码或名称模糊搜索|
|status|string|`active` / `inactive`|

### 响应示例

```json
{
  "items": [
    {
      "id": "tag-uuid-1",
      "tag_code": "earnings_beat",
      "tag_name": "业绩超预期",
      "tag_type": "event",
      "parent_id": null,
      "status": "active"
    }
  ]
}
```

---

## 6.2 `POST /api/v1/tags`

### 用途

- 创建标签

### 请求体示例

```json
{
  "tag_code": "earnings_beat",
  "tag_name": "业绩超预期",
  "tag_type": "event",
  "parent_id": null,
  "description": "业绩明显高于市场预期"
}
```

---

## 6.3 `PUT /api/v1/tags/{tag_id}`

### 用途

- 更新标签名称、描述、状态

### 请求体示例

```json
{
  "tag_name": "业绩超预期",
  "description": "业绩高于一致预期或公司指引",
  "status": "active"
}
```

---

## 6.4 `POST /api/v1/documents/{document_id}/tags`

### 用途

- 给文档添加标签

### 请求体示例

```json
{
  "tag_ids": ["tag-uuid-1", "tag-uuid-2"]
}
```

---

## 6.5 `GET /api/v1/documents/{document_id}/tags`

### 用途

- 查询文档已关联标签

### 响应示例

```json
{
  "items": [
    {
      "id": "tag-uuid-1",
      "tag_code": "earnings_beat",
      "tag_name": "业绩超预期",
      "tag_type": "event"
    }
  ]
}
```

---

## 6.6 `DELETE /api/v1/documents/{document_id}/tags/{tag_id}`

### 用途

- 移除文档标签

---

## 6.7 `POST /api/v1/assets/{asset_id}/tags`

### 用途

- 给研究资产添加标签

### 请求体示例

```json
{
  "tag_ids": ["tag-uuid-1", "tag-uuid-2"]
}
```

---

## 6.8 `GET /api/v1/assets/{asset_id}/tags`

### 用途

- 查询研究资产已关联标签

### 响应示例

```json
{
  "items": [
    {
      "id": "tag-uuid-1",
      "tag_code": "earnings_beat",
      "tag_name": "业绩超预期",
      "tag_type": "event"
    }
  ]
}
```

---

## 6.9 `DELETE /api/v1/assets/{asset_id}/tags/{tag_id}`

### 用途

- 移除研究资产标签

---

## 7. 文档接口

## 7.1 `POST /api/v1/documents`

### 用途

- 上传原始文档
- 保存文档元数据
- 创建 `documents` 主记录

### 请求方式

- `multipart/form-data`

### 请求字段

|字段|类型|必填|说明|
|---|---|---|---|
|file|file|是|原始文件|
|title|string|否|标题，不传则默认文件名|
|doc_type|string|是|`report` / `announcement` / `financial_report` / `memo`|
|source|string|否|来源机构或来源渠道|
|company_code|string|否|公司代码|
|company_name|string|否|公司名称快照|
|industry|string|否|行业快照|
|publish_date|string|否|发布日期，格式 `YYYY-MM-DD`|
|permission_level|string|否|权限级别，默认 `internal`|
|tag_ids|string[]|否|初始标签|

### 响应示例

```json
{
  "document_id": "8d8a3f5a-xxxx",
  "source_id": "doc_20260604_0001",
  "parse_status": "pending"
}
```

### 兼容说明

- 如果已经实现过旧接口，`POST /documents/upload` 可作为兼容别名保留到一期结束

---

## 7.2 `POST /api/v1/documents/batch-upload`

### 用途

- 批量上传文档
- 适合一次导入 20-50 份样本研报

### 请求方式

- `multipart/form-data`

### 请求字段

|字段|类型|必填|说明|
|---|---|---|---|
|files|file[]|是|多个文档文件|
|common_metadata|json|string|公共元数据，如公司、文档类型、权限|

### 响应示例

```json
{
  "items": [
    {
      "file_name": "report_600519.pdf",
      "document_id": "doc-uuid-1",
      "source_id": "doc_20260604_0001",
      "parse_status": "pending"
    }
  ],
  "failed_items": []
}
```

---

## 7.3 `POST /api/v1/documents/{document_id}/ingest`

### 用途

- 触发文档解析、切分、向量化、入库

### 请求体示例

```json
{
  "force_reingest": false,
  "parse_strategy_version": "v1",
  "chunk_size": 800,
  "chunk_overlap": 120
}
```

### 响应示例

```json
{
  "task_id": "2f5f0d3f-xxxx",
  "status": "pending"
}
```

---

## 7.4 `POST /api/v1/documents/batch-ingest`

### 用途

- 批量触发文档解析入库

### 请求体示例

```json
{
  "document_ids": ["doc-uuid-1", "doc-uuid-2"],
  "force_reingest": false
}
```

---

## 7.5 `GET /api/v1/documents`

### 用途

- 文档列表查询

### 查询参数

|参数|类型|说明|
|---|---|---|
|doc_type|string|按类型过滤|
|company_code|string|按公司过滤|
|keyword|string|标题模糊搜索|
|parse_status|string|按解析状态过滤|
|source|string|来源机构过滤|
|tag_code|string|标签过滤|
|publish_date_start|string|发布日期开始|
|publish_date_end|string|发布日期结束|
|permission_level|string|权限级别过滤|
|page|int|页码|
|page_size|int|每页数量|
|sort_by|string|排序字段|
|sort_order|string|排序方向|

### 响应示例

```json
{
  "items": [
    {
      "id": "8d8a3f5a-xxxx",
      "source_id": "doc_20260604_0001",
      "title": "贵州茅台2025年年报",
      "doc_type": "financial_report",
      "company_code": "600519",
      "company_name": "贵州茅台",
      "source": "上交所",
      "publish_date": "2026-03-28",
      "parse_status": "parsed",
      "tag_names": ["年报", "白酒"]
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

---

## 7.6 `GET /api/v1/documents/{document_id}`

### 用途

- 获取文档详情

### 返回内容

- 元数据
- 标签
- 解析状态
- chunk 数量
- 最近处理任务
- 解析错误信息

---

## 7.7 `GET /api/v1/documents/{document_id}/chunks`

### 用途

- 查看文档切分结果
- 调试 RAG chunk 质量

### 查询参数

|参数|类型|说明|
|---|---|---|
|page|int|页码|
|page_size|int|每页数量|
|content_type|string|内容类型|
|page_no|int|页码过滤|
|is_important|boolean|是否重点片段|

### 响应示例

```json
{
  "items": [
    {
      "id": "chunk-uuid-1",
      "chunk_id": "c_001",
      "chunk_index": 1,
      "chunk_text": "公司收入增长主要来自...",
      "content_type": "paragraph",
      "page_no": 12,
      "position_start": 1200,
      "position_end": 1680,
      "section_title": "经营分析",
      "section_path": "第三章>经营分析>收入结构",
      "token_count": 236,
      "summary_text": "收入增长原因摘要",
      "keywords_json": ["收入", "增长", "直营"],
      "entities_json": {
        "companies": ["贵州茅台"],
        "products": ["飞天茅台"]
      },
      "is_important": true
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

说明：

- 默认不返回 embedding 向量，避免响应过大

---

## 7.8 `GET /api/v1/documents/{document_id}/preview`

### 用途

- 返回原始文档提取后的预览文本

### 查询参数

|参数|类型|默认值|说明|
|---|---:|---:|---|
|max_chars|int|5000|最大返回字符数|

---

## 7.9 `DELETE /api/v1/documents/{document_id}`

### 用途

- 软删除文档
- 同步隐藏文档 chunks、标签关系和检索结果

### 响应示例

```json
{
  "document_id": "doc-uuid-1",
  "deleted": true
}
```

---

## 7.10 `DELETE /api/v1/documents/batch-delete`

### 用途

- 批量软删除文档

### 请求体示例

```json
{
  "document_ids": ["doc-uuid-1", "doc-uuid-2"]
}
```

---

## 7.11 `GET /api/v1/documents/trash`

### 用途

- 查询已软删除文档
- 用于误删恢复前的人工确认

### 查询参数

|参数|类型|说明|
|---|---|---|
|keyword|string|标题模糊搜索|
|company_code|string|公司过滤|
|deleted_date_start|string|删除日期开始|
|deleted_date_end|string|删除日期结束|
|page|int|页码|
|page_size|int|每页数量|

### 响应示例

```json
{
  "items": [
    {
      "document_id": "doc-uuid-1",
      "title": "贵州茅台2025年年报",
      "company_code": "600519",
      "deleted_at": "2026-06-04T16:30:00+08:00"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

---

## 8. 检索与问答接口

## 8.1 `POST /api/v1/search/retrieve`

### 用途

- 执行向量检索、关键词检索或混合检索
- 返回相关 chunk
- 单独暴露检索接口，便于调试召回和重排质量

### 请求体示例

```json
{
  "query": "茅台近期业绩增长的主要原因是什么？",
  "filters": {
    "company_codes": ["600519"],
    "doc_types": ["report", "announcement", "financial_report"],
    "industries": ["食品饮料"],
    "tag_codes": ["earnings_beat"],
    "publish_date_start": "2025-01-01",
    "publish_date_end": "2025-12-31",
    "sources": ["中金公司", "中信证券"],
    "permission_level": "internal"
  },
  "retrieval_strategy": "hybrid",
  "hybrid_weights": {
    "vector": 0.6,
    "keyword": 0.4
  },
  "ranking_strategy": "rerank",
  "top_k": 10,
  "expand_context": true
}
```

### 参数说明

|参数|类型|说明|
|---|---|---|
|retrieval_strategy|string|`vector` / `keyword` / `hybrid`|
|ranking_strategy|string|`none` / `rerank` / `weighted`|
|expand_context|boolean|是否扩展相邻 chunk 作为上下文|

### 响应示例

```json
{
  "items": [
    {
      "chunk_id": "chunk-uuid-1",
      "document_id": "8d8a3f5a-xxxx",
      "source_id": "doc_20260604_0001",
      "title": "贵州茅台2025年年报",
      "page_no": 12,
      "section_path": "第三章>经营分析",
      "score": 0.9123,
      "vector_score": 0.88,
      "keyword_score": 0.72,
      "rerank_score": 0.91,
      "chunk_text": "..."
    }
  ],
  "retrieval_strategy": "hybrid",
  "ranking_strategy": "rerank"
}
```

---

## 8.2 `POST /api/v1/qa/ask`

### 用途

- 执行带引用问答
- 同步返回完整答案

### 请求体示例

```json
{
  "question": "总结一下茅台 2025 年经营亮点",
  "filters": {
    "company_codes": ["600519"],
    "doc_types": ["report", "announcement", "financial_report"],
    "tag_codes": ["earnings_beat"],
    "permission_level": "internal"
  },
  "retrieval_strategy": "hybrid",
  "ranking_strategy": "rerank",
  "top_k": 6,
  "model_name": "default",
  "template_key": "research_qa_default"
}
```

### 响应示例

```json
{
  "task_id": "a111-xxxx",
  "answer": "茅台 2025 年经营亮点主要包括直销渠道增长、产品结构改善和费用率控制[1][2]。",
  "citations": [
    {
      "citation_no": 1,
      "document_id": "doc-uuid-1",
      "chunk_id": "chunk-uuid-1",
      "source_id": "doc_20260604_0001",
      "title": "贵州茅台2025年年报",
      "page_no": 12,
      "quote_text": "直销渠道收入同比提升..."
    }
  ]
}
```

### 引用规范

- `answer` 字段中必须包含 `[1]`、`[2]` 形式的引用标记
- 引用编号必须与 `citations[].citation_no` 一一对应
- `citations` 应写入 `citations` 表，并关联 `task_id`

---

## 8.3 `POST /api/v1/qa/ask/stream`

### 用途

- 执行带引用问答
- 使用 SSE 流式返回生成过程

### 请求头

```text
Content-Type: application/json
Accept: text/event-stream
```

### 请求体

与 `POST /api/v1/qa/ask` 相同。

### SSE 事件示例

```text
event: status
data: {"task_id":"a111-xxxx","status":"retrieving"}

event: citation
data: {"citation_no":1,"source_id":"doc_20260604_0001","page_no":12}

event: chunk
data: {"delta":"茅台 2025 年经营亮点主要包括"}

event: done
data: {"task_id":"a111-xxxx","answer":"完整答案[1]","citations":[...]}
```

---

## 8.4 `POST /api/v1/qa/memo-generate`

### 用途

- 基于公司、主题和模板生成研究备忘录草稿
- 生成结果不自动保存为资产，用户修订后调用 `POST /api/v1/assets` 保存

### 请求体示例

```json
{
  "title": "茅台投资逻辑跟踪",
  "company_code": "600519",
  "query_focus": ["经营亮点", "风险因素", "估值变化"],
  "filters": {
    "doc_types": ["report", "announcement", "financial_report"],
    "tag_codes": ["earnings_beat"],
    "publish_date_start": "2025-01-01"
  },
  "template_key": "research_memo_default",
  "top_k": 12
}
```

### 响应示例

```json
{
  "task_id": "memo-task-001",
  "asset_type": "research_memo",
  "title": "茅台投资逻辑跟踪",
  "content_markdown": "# 茅台投资逻辑跟踪\n...",
  "citations": []
}
```

---

## 8.5 `POST /api/v1/qa/daily-report-generate`

### 用途

- 生成晨会日报草稿
- 支持模板选择

### 请求体示例

```json
{
  "report_date": "2026-06-04",
  "market_summary": true,
  "include_companies": ["600519", "000858"],
  "include_recent_assets": true,
  "template_key": "daily_report_default",
  "filters": {
    "doc_types": ["announcement", "financial_report"],
    "publish_date_start": "2026-06-03",
    "publish_date_end": "2026-06-04"
  }
}
```

### 响应示例

```json
{
  "task_id": "daily-task-001",
  "asset_type": "daily_report",
  "content_markdown": "# 晨会日报\n...",
  "citations": []
}
```

---

## 9. 任务接口

## 9.1 `POST /api/v1/tasks`

### 用途

- 用统一入口创建任务
- 由总控 Agent 识别类型并路由

### 请求体示例

```json
{
  "task_type": "qa",
  "task_title": "茅台公告要点总结",
  "input_text": "总结一下茅台近期公告要点",
  "input_payload": {
    "company_code": "600519",
    "top_k": 6
  },
  "priority": "normal"
}
```

### 响应示例

```json
{
  "task_id": "task-001",
  "status": "pending",
  "route_agent": "research_agent"
}
```

### 调用建议

- 简单前端可以直接调用 `/qa/ask`、`/qa/memo-generate`
- 需要统一任务追踪、Agent 路由、异步执行时，推荐调用 `/tasks`
- 两种方式都应写入 `tasks` 和 `task_runs`

### 状态流转

```text
pending -> running -> succeeded
pending -> running -> failed
pending -> cancelled
```

说明：

- `/documents/{document_id}/ingest` 返回的 `task_id` 也遵循同一状态流转
- `failed` 状态必须返回 `error_message`
- `succeeded` 状态应写入 `output_payload` 和 `result_summary`

---

## 9.2 `GET /api/v1/tasks`

### 用途

- 查询任务列表

### 查询参数

|参数|类型|说明|
|---|---|---|
|task_type|string|任务类型|
|status|string|任务状态|
|route_agent|string|路由 Agent|
|created_by|string|创建人|
|page|int|页码|
|page_size|int|每页数量|

---

## 9.3 `GET /api/v1/tasks/{task_id}`

### 用途

- 查询任务详情

### 返回内容

- 任务基本信息
- 当前状态
- 路由 Agent
- 输入摘要
- 输出摘要
- 错误信息
- 开始和结束时间

---

## 9.4 `GET /api/v1/tasks/{task_id}/runs`

### 用途

- 查看任务执行过程
- 排查 Agent/Skill 执行问题

### 响应示例

```json
{
  "items": [
    {
      "run_id": "run-uuid-1",
      "run_type": "skill",
      "run_name": "hybrid_retrieval",
      "status": "succeeded",
      "duration_ms": 835,
      "error_message": null,
      "created_at": "2026-06-04T16:10:00+08:00"
    }
  ]
}
```

---

## 10. 研究资产接口

## 10.1 `POST /api/v1/assets`

### 用途

- 保存研究备忘录、晨会日报或其他研究资产
- 写入 `research_assets`
- 同步写入 `citations` 和 `asset_sources`

### 请求体示例

```json
{
  "asset_type": "research_memo",
  "title": "茅台投资逻辑跟踪",
  "content_markdown": "# 茅台投资逻辑跟踪\n...",
  "summary": "本文跟踪茅台经营亮点、风险与估值变化。",
  "company_code": "600519",
  "industry": "食品饮料",
  "task_id": "memo-task-001",
  "tag_ids": ["tag-uuid-1"],
  "citations": [
    {
      "citation_no": 1,
      "document_id": "doc-uuid-1",
      "chunk_id": "chunk-uuid-1",
      "source_id": "doc_20260604_0001",
      "page_no": 12,
      "quote_text": "..."
    }
  ]
}
```

### 响应示例

```json
{
  "asset_id": "asset-001",
  "version": 1,
  "status": "draft"
}
```

---

## 10.2 `GET /api/v1/assets`

### 用途

- 查询研究资产列表

### 查询参数

|参数|类型|说明|
|---|---|---|
|asset_type|string|资产类型|
|company_code|string|公司代码|
|status|string|资产状态|
|keyword|string|标题或摘要搜索|
|tag_code|string|标签过滤|
|created_by|string|创建人|
|page|int|页码|
|page_size|int|每页数量|

---

## 10.3 `GET /api/v1/assets/{asset_id}`

### 用途

- 获取研究资产详情

### 返回内容

- 正文
- 摘要
- 标签
- 引用
- 来源任务
- 来源文档和 chunk
- 当前版本

---

## 10.4 `PUT /api/v1/assets/{asset_id}`

### 用途

- 更新研究资产
- 支持人工修订
- 每次更新自动创建 `asset_revisions` 记录，并递增版本号

### 请求体示例

```json
{
  "title": "茅台投资逻辑跟踪（修订）",
  "content_markdown": "# 修订版\n...",
  "summary": "修订后摘要",
  "status": "draft",
  "updated_by": "user-001",
  "change_note": "补充估值变化"
}
```

### 响应示例

```json
{
  "asset_id": "asset-001",
  "version": 2,
  "status": "draft"
}
```

---

## 10.5 `GET /api/v1/assets/{asset_id}/revisions`

### 用途

- 查询资产版本历史

### 响应示例

```json
{
  "items": [
    {
      "version": 1,
      "summary": "初版摘要",
      "updated_by": "user-001",
      "change_note": "初次保存",
      "created_at": "2026-06-04T16:00:00+08:00"
    }
  ]
}
```

---

## 10.6 `GET /api/v1/assets/{asset_id}/revisions/{version}`

### 用途

- 获取指定版本内容

### 响应示例

```json
{
  "asset_id": "asset-001",
  "version": 1,
  "content_markdown": "# 初版\n...",
  "summary": "初版摘要",
  "change_note": "初次保存"
}
```

---

## 10.7 `POST /api/v1/assets/{asset_id}/rollback`

### 用途

- 回滚到指定版本
- 回滚操作本身应生成一个新版本

### 请求体示例

```json
{
  "target_version": 1,
  "updated_by": "user-001",
  "change_note": "回滚到初版"
}
```

---

## 10.8 `POST /api/v1/assets/{asset_id}/export`

### 用途

- 导出 Markdown 或 DOCX

### 请求体示例

```json
{
  "format": "docx"
}
```

### 参数说明

- `format` 支持 `markdown`、`md`、`docx`

### 响应示例

```json
{
  "file_name": "memo_600519_20260604.docx",
  "download_path": "/exports/memo_600519_20260604.docx"
}
```

---

## 10.9 `DELETE /api/v1/assets/{asset_id}`

### 用途

- 软删除研究资产

### 响应示例

```json
{
  "asset_id": "asset-001",
  "deleted": true
}
```

---

## 11. 模板与配置接口

## 11.1 `GET /api/v1/prompts`

### 用途

- 查询 Prompt 模板列表

### 查询参数

|参数|类型|说明|
|---|---|---|
|agent_name|string|所属 Agent|
|scenario|string|场景，如 `qa`、`research_memo`、`daily_report`|
|status|string|模板状态|

---

## 11.2 `POST /api/v1/prompts`

### 用途

- 新增 Prompt 模板

### 请求体示例

```json
{
  "template_key": "research_memo_default",
  "template_name": "研究备忘录默认模板",
  "agent_name": "report_agent",
  "scenario": "research_memo",
  "content": "请基于以下材料生成研究备忘录...",
  "status": "active"
}
```

### 说明

- `/qa/ask`、`/qa/memo-generate`、`/qa/daily-report-generate` 通过 `template_key` 引用模板

---

## 11.3 `GET /api/v1/configs`

### 用途

- 查询系统配置

### 典型配置

- `chunk_size`
- `chunk_overlap`
- `retrieval_top_k`
- `rerank_enabled`
- `default_llm_model`
- `default_embedding_model`

---

## 11.4 `PUT /api/v1/configs/{config_key}`

### 用途

- 更新系统参数

### 请求体示例

```json
{
  "config_value": {
    "value": 800
  },
  "description": "默认 chunk 大小"
}
```

---

## 12. 统计看板接口

统计接口用于本地调试、验收和简单运营看板，不影响第一期主业务闭环，可以放到 P3。

## 12.1 `GET /api/v1/stats/documents`

### 用途

- 查询文档统计
- 按文档类型、解析状态、日期统计

### 查询参数

|参数|类型|说明|
|---|---|---|
|date_start|string|开始日期|
|date_end|string|结束日期|
|group_by|string|`doc_type` / `parse_status` / `source` / `date`|

### 响应示例

```json
{
  "total": 128,
  "by_doc_type": {
    "report": 60,
    "announcement": 42,
    "financial_report": 26
  },
  "by_parse_status": {
    "parsed": 120,
    "failed": 8
  }
}
```

---

## 12.2 `GET /api/v1/stats/retrieval`

### 用途

- 查询检索统计
- 用于评估检索调用量、平均耗时、无结果比例

### 响应示例

```json
{
  "total_queries": 320,
  "empty_result_count": 18,
  "empty_result_rate": 0.0563,
  "avg_latency_ms": 842
}
```

---

## 12.3 `GET /api/v1/stats/assets`

### 用途

- 查询研究资产统计
- 按资产类型、状态、公司统计

### 响应示例

```json
{
  "total": 35,
  "by_asset_type": {
    "research_memo": 22,
    "daily_report": 13
  },
  "by_status": {
    "draft": 30,
    "published": 5
  }
}
```

---

## 12.4 `GET /api/v1/stats/tasks`

### 用途

- 查询任务统计
- 用于评估任务成功率、失败率和平均耗时

### 响应示例

```json
{
  "total": 420,
  "by_status": {
    "succeeded": 390,
    "failed": 20,
    "cancelled": 10
  },
  "success_rate": 0.9286,
  "avg_duration_ms": 1680
}
```

---

## 13. 第一期优先落地接口顺序

### P0：必须先做

- `GET /health`
- `GET /api/v1/system/info`
- `GET /api/v1/companies`
- `GET /api/v1/companies/{company_code}`
- `POST /api/v1/documents`
- `POST /api/v1/documents/{document_id}/ingest`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/documents/{document_id}/chunks`
- `POST /api/v1/search/retrieve`
- `POST /api/v1/qa/ask`
- `POST /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`

### P1：一期建议补齐

- `GET /api/v1/tags`
- `POST /api/v1/tags`
- `POST /api/v1/documents/{document_id}/tags`
- `GET /api/v1/documents/{document_id}/tags`
- `DELETE /api/v1/documents/{document_id}/tags/{tag_id}`
- `POST /api/v1/qa/ask/stream`
- `POST /api/v1/qa/memo-generate`
- `POST /api/v1/qa/daily-report-generate`
- `POST /api/v1/assets`
- `GET /api/v1/assets`
- `GET /api/v1/assets/{asset_id}`
- `PUT /api/v1/assets/{asset_id}`
- `POST /api/v1/assets/{asset_id}/export`
- `GET /api/v1/prompts`
- `POST /api/v1/prompts`

### P2：一期后段或二期前补

- `POST /api/v1/companies`
- `PUT /api/v1/tags/{tag_id}`
- `POST /api/v1/assets/{asset_id}/tags`
- `GET /api/v1/assets/{asset_id}/tags`
- `DELETE /api/v1/assets/{asset_id}/tags/{tag_id}`
- `GET /api/v1/assets/{asset_id}/revisions`
- `GET /api/v1/assets/{asset_id}/revisions/{version}`
- `POST /api/v1/assets/{asset_id}/rollback`
- `DELETE /api/v1/documents/{document_id}`
- `DELETE /api/v1/assets/{asset_id}`

### P3：效率增强

- `POST /api/v1/documents/batch-upload`
- `POST /api/v1/documents/batch-ingest`
- `DELETE /api/v1/documents/batch-delete`
- `GET /api/v1/documents/trash`
- `GET /api/v1/configs`
- `PUT /api/v1/configs/{config_key}`
- `GET /api/v1/stats/documents`
- `GET /api/v1/stats/retrieval`
- `GET /api/v1/stats/assets`
- `GET /api/v1/stats/tasks`

---

## 14. 为二期和三期预留的接口思路

### 二期可扩展

- `/api/v1/factors/*`
- `/api/v1/backtests/*`
- `/api/v1/sandbox/*`

### 三期可扩展

- `/api/v1/portfolio/*`
- `/api/v1/risk/*`
- `/api/v1/approvals/*`

这样设计的原因：

- 一期先把资源和任务边界定清楚
- 二期三期只是在此基础上增加新资源和新任务，不需要推翻接口风格

---

## 15. v2 重点优化总结

相较于原接口文档，v2 重点补强：

1. 增加 `/api/v1` 版本前缀
2. 补齐公司主数据接口，对齐 `company_basic_info`
3. 补齐标签接口，对齐 `tags`、`document_tags`、`research_asset_tags`
4. 强化检索请求参数，支持多公司、日期、来源、标签、权限、混合检索和重排
5. 增加问答流式接口，改善 LLM 等待体验
6. 明确引用编号规范，并要求引用写入 `citations`
7. 增加模板选择参数 `template_key`
8. 补齐资产版本历史、指定版本查询和回滚接口
9. 增加文档批量上传、批量入库、批量删除接口
10. 统一分页结构、状态枚举和错误码
11. 补充文档/资产标签查询、文档回收站和统计看板接口
