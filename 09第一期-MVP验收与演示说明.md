# 第一期 MVP 验收与演示说明

> 更新日期：2026-06-07
> 当前目标：验证第一期本地 MVP 是否具备“文档接入 -> 检索 -> 问答 -> Agent 路由 -> 研究输出 -> 资产沉淀”的可演示闭环。

## 1. 当前可演示能力

### 1.1 文档接入

- 支持 TXT、Markdown、PDF、DOCX 等文件上传。
- 支持文档解析、切分、embedding 写入 `document_chunks`。
- 支持文档详情、chunk 列表、预览、软删除。

### 1.2 检索与问答

- 支持混合检索：关键词相似度 + pgvector 向量相似度。
- 支持 DeepSeek LLM 生成带引用回答。
- `/api/v1/qa/ask` 会自动创建或接管 QA task，并写入 `task_runs`。
- citations 会保存到 `citations` 表，并关联 task 或 asset。

### 1.3 Agent/Skill 最小闭环

- 新增最小 Skill 注册表。
- 新增总控 Agent 路由入口：`POST /api/v1/agents/route`。
- 当前可路由任务：
  - QA：`research.qa`
  - 研究备忘录：`research.memo`
  - 研究日报：`report.daily`
  - 文档入库：已识别路由，执行逻辑待补。

### 1.4 研究输出与资产沉淀

- `/api/v1/qa/memo` 生成结构化研究备忘录，并保存为 `research_assets`。
- `/api/v1/qa/daily-report` 生成结构化研究日报，并保存为 `research_assets`。
- 资产支持列表、详情、更新、版本记录、Markdown/DOCX 导出。

## 2. 演示流程

### Step 1：启动服务

```bash
uvicorn app.main:app --reload --port 8000
```

### Step 2：检查系统状态

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/system/info
```

确认：

- `vector_enabled=true`
- `llm_configured=true`
- `embedding_provider=ollama-local`

### Step 3：运行自动演示脚本

```bash
python scripts/smoke_api.py
```

该脚本会自动验证：

- 上传 TXT/DOCX/PDF
- ingest 入库
- 检索命中
- QA 生成答案
- QA task 完成
- task_runs 写入
- citations 按 task 保存
- 总控 Agent 路由 QA
- 研究备忘录生成并保存资产
- 研究日报生成并保存资产
- citations 按 asset 保存
- 资产导出

### Step 4：运行检索评估

```bash
python scripts/eval_retrieval.py --cases evals/retrieval_cases.jsonl
```

当前样例集目标：验证核心关键词是否能在 top-k 召回中命中。

### Step 5：运行测试

```bash
pytest -q
```

## 3. 当前验收结果

最近一次验证结果：

- `pytest -q`：12 passed
- `scripts/eval_retrieval.py`：12/12 passed
- `scripts/smoke_api.py`：通过

## 4. 已知限制

- Agent/Skill 目前是最小协议，尚未形成复杂 Planner。
- 文档入库路由已识别，但还没有作为 Skill 执行。
- 研究备忘录和日报已结构化，但模板仍偏轻量，后续需要结合正式投研模板优化。
- 检索评估样本还是小样本，尚未覆盖 20-50 份真实研报/公告。
- 前端界面尚未建设，当前以 API 和脚本演示为主。

## 5. 一期剩余收尾建议

1. 用 20-50 份真实研报/公告做解析回归。
2. 增加真实投研模板：公司快评、行业日报、会议纪要摘要。
3. 将文档入库也注册为 Skill，并由总控 Agent 执行。
4. 为 Agent 路由、memo、daily-report 增加单独测试文件。
5. 清理 smoke 测试产生的重复样本文档或增加测试数据隔离策略。
