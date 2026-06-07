from pathlib import Path

from pydantic import ValidationError

from app.api.routers.documents import IngestRequest
from app.api.routers.qa import AskRequest
from app.api.routers.search import SearchRequest
from app.agents.base_agent import AgentTaskInput, AgentTaskOutput
from app.agents.base_agent import AgentContext
from app.agents.reporting_agent import ReportingAgent
from app.agents.research_agent import ResearchAgent
from app.agents.orchestrator_agent import decide_route
from app.agents.registry import AgentRegistry
from app.agents.supervisor import route_task
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db import session as db_session
from app.services import assets as assets_service
from app.services import documents as documents_service
from app.services.embeddings import embed_text, embedding_provider, vector_literal
from app.services import llm as llm_service
from app.services.llm import generate_answer, generate_answer_stream
from app.services.prompts import DEFAULT_PROMPT_TEMPLATES, get_default_prompt_content, render_prompt_template
from app.services.reports import DAILY_TEMPLATE, _render_daily_report_prompt, _render_report_prompt
from app.services.search import answer_question, execute_qa_task, hybrid_search, save_citations, stream_answer_question
from app.services.tasks import execute_task
from app.services.text import split_chunks


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.executed = []
        self._index = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        if self._index >= len(self.rows):
            return None
        row = self.rows[self._index]
        self._index += 1
        return row

    def fetchall(self):
        if self._index >= len(self.rows):
            return []
        rows = self.rows[self._index]
        self._index += 1
        return rows


class FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(self, rows=None):
        self.cursor_obj = FakeCursor(rows=rows)

    def cursor(self):
        return self.cursor_obj

    def transaction(self):
        return FakeTransaction()


def test_local_hash_embedding_shape_and_provider(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local_hash")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "")
    monkeypatch.setenv("EMBEDDING_API_KEY", "")
    get_settings.cache_clear()

    vector = embed_text("贵州茅台 直营渠道 收入增长")

    assert embedding_provider() == "local_hash"
    assert len(vector) == 1024
    assert any(value != 0 for value in vector)
    get_settings.cache_clear()


def test_vector_literal_format():
    assert vector_literal([0.1, -0.2]) == "[0.10000000,-0.20000000]"


def test_get_conn_uses_pool_and_commits(monkeypatch):
    class FakeConnection:
        committed = False
        rolled_back = False

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

    class FakeConnectionContext:
        exited = False

        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, exc_type, exc, traceback):
            self.exited = True

    class FakePool:
        def __init__(self, context):
            self.context = context

        def connection(self):
            return self.context

    conn = FakeConnection()
    context = FakeConnectionContext(conn)
    monkeypatch.setattr(db_session, "_pool", FakePool(context))

    dependency = db_session.get_conn()

    assert next(dependency) is conn
    try:
        next(dependency)
    except StopIteration:
        pass

    assert conn.committed is True
    assert conn.rolled_back is False
    assert context.exited is True


def test_llm_fallback_without_config(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()

    answer, provider = generate_answer("收入增长原因是什么？", [])

    assert provider == "fallback"
    assert "未检索到" in answer
    get_settings.cache_clear()


def test_llm_stream_fallback_without_config(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()

    chunks, provider = generate_answer_stream("收入增长原因是什么？", [])

    assert provider == "fallback"
    assert "".join(chunks) == "未检索到足够相关的本地文档片段，暂无法基于资料回答。"
    get_settings.cache_clear()


def test_extract_stream_delta_supports_string_and_list_content():
    assert llm_service._extract_stream_delta({"choices": [{"delta": {"content": "直营渠道"}}]}) == "直营渠道"
    assert llm_service._extract_stream_delta(
        {"choices": [{"delta": {"content": [{"type": "text", "text": "收入增长"}, {"type": "ignored", "text": "x"}]}}]}
    ) == "收入增长"


def test_default_prompt_templates_include_runnable_keys():
    keys = {template["template_key"] for template in DEFAULT_PROMPT_TEMPLATES}

    assert {
        "llm.system.default",
        "research.qa.rag",
        "research.memo",
        "research.daily_report",
        "research.summary",
        "research.conclusion",
    }.issubset(keys)

    rendered = render_prompt_template(
        get_default_prompt_content("research.qa.rag"),
        {"question": "收入增长原因是什么？", "context": "[1] 财报\n直营渠道增长"},
    )

    assert "收入增长原因是什么？" in rendered
    assert "直营渠道增长" in rendered


def test_search_request_validates_top_k():
    try:
        SearchRequest(query="渠道", top_k=0)
    except ValidationError:
        return
    raise AssertionError("top_k=0 should fail validation")


def test_ask_request_requires_question():
    try:
        AskRequest(question="", top_k=5)
    except ValidationError:
        return
    raise AssertionError("empty question should fail validation")


def test_ingest_request_rejects_invalid_overlap():
    try:
        IngestRequest(chunk_size=300, chunk_overlap=300)
    except ValidationError:
        return
    raise AssertionError("chunk_overlap >= chunk_size should fail validation")


def test_split_chunks_preserves_paragraph_boundaries():
    text = (
        "一、投资要点\n\n"
        "贵州茅台收入增长主要来自直营渠道扩张和产品结构优化，直营占比提升带动渠道利润改善。\n\n"
        "公司现金流稳定，毛利率保持高位，费用率整体可控。"
    )

    chunks = split_chunks(text, chunk_size=60, chunk_overlap=0)

    assert len(chunks) >= 2
    assert chunks[0].startswith("一、投资要点")
    assert "直营渠道扩张" in chunks[0]
    assert "现金流稳定" in chunks[-1]


def test_split_chunks_carries_heading_context():
    text = "一、投资要点\n\n贵州茅台收入增长主要来自直营渠道扩张和产品结构优化。\n\n公司现金流稳定，毛利率保持高位。"

    chunks = split_chunks(text, chunk_size=55, chunk_overlap=20)

    assert any(chunk.startswith("一、投资要点") and "现金流稳定" in chunk for chunk in chunks)


def test_split_chunks_carries_page_context():
    text = "[page 3]\n\n白酒行业需求韧性较强，但渠道库存需要持续观察。"

    chunks = split_chunks(text, chunk_size=80, chunk_overlap=0)

    assert chunks == ["[page 3]\n白酒行业需求韧性较强，但渠道库存需要持续观察。"]


def test_agent_route_decides_research_qa():
    decision = decide_route({"question": "贵州茅台收入增长原因是什么？"})

    assert decision.task_type == "qa"
    assert decision.agent == "research_agent"
    assert decision.skill == "research.qa"


def test_agent_registry_returns_default_agent():
    registry = AgentRegistry()
    registry.register(ResearchAgent(), default=True)

    assert registry.default().name == "research_agent"
    assert registry.list() == [
        {
            "name": "research_agent",
            "description": "Handle research retrieval, QA, summaries, memos, and conclusions through research skills.",
        }
    ]


def test_agent_route_decides_research_summary_and_conclusion():
    summary = decide_route({"task_type": "summary", "topic": "白酒行业渠道库存"})
    conclusion = decide_route({"task_type": "conclusion", "topic": "贵州茅台收入增长"})

    assert summary.agent == "research_agent"
    assert summary.skill == "research.summary"
    assert conclusion.agent == "research_agent"
    assert conclusion.skill == "research.conclusion"


def test_agent_route_decides_reporting_tasks():
    weekly = decide_route({"task_type": "weekly_report", "topic": "白酒行业周报"})
    brief = decide_route({"task_type": "investment_brief", "topic": "贵州茅台投决材料"})

    assert weekly.agent == "report_agent"
    assert weekly.skill == "report.weekly"
    assert brief.agent == "report_agent"
    assert brief.skill == "report.investment_brief"


def test_agent_route_defaults_to_research_qa_for_task_execution():
    decision = decide_route({"task_type": "qa", "input_text": "总结茅台收入增长原因"})

    assert decision.agent == "research_agent"
    assert decision.skill == "research.qa"


def test_agent_task_input_and_output_contract():
    task_input = AgentTaskInput.from_payload(
        {
            "task_type": "memo",
            "topic": "白酒行业渠道库存",
            "task_id": "task-1",
            "asset_id": "asset-1",
        },
        request_id="req-1",
    )

    assert task_input.task_type == "memo"
    assert task_input.input_text == "白酒行业渠道库存"
    assert task_input.request_id == "req-1"
    assert task_input.to_payload()["task_id"] == "task-1"

    output = AgentTaskOutput(
        agent="research_agent",
        task_type="memo",
        status="completed",
        skill="research.memo",
        result={"title": "备忘录"},
    )

    assert output.to_dict() == {
        "agent": "research_agent",
        "task_type": "memo",
        "status": "completed",
        "result": {"title": "备忘录"},
        "skill": "research.memo",
    }


def test_report_prompt_template_renders_known_placeholders():
    prompt = _render_report_prompt(
        template="# {title}\n\n{evidence}\n\n{references}",
        topic="贵州茅台",
        title="贵州茅台 - 研究备忘录",
        qa_answer="收入增长来自直营渠道。",
        evidence="- 文档：财报\n  - 直营渠道收入增长 [1]",
        references="- [1] 财报 / chunk=1",
        risks="- 渠道库存待验证",
    )

    assert "贵州茅台 - 研究备忘录" in prompt
    assert "直营渠道收入增长" in prompt
    assert "chunk=1" in prompt


def test_daily_report_template_has_morning_brief_sections():
    markdown = DAILY_TEMPLATE.format(
        title="晨会日报",
        market_summary="- 市场波动收敛 [1]",
        announcement_summary="- 公司公告披露分红方案 [2]",
        news_summary="- 行业新闻提到需求恢复 [3]",
        research_viewpoints="- 券商观点偏积极 [4]",
        risks="- 渠道库存待验证",
        references="- [1] 市场日报 / chunk=1",
    )

    assert "## 市场概览" in markdown
    assert "## 公告跟踪" in markdown
    assert "## 新闻动态" in markdown
    assert "## 研究观点" in markdown


def test_daily_report_prompt_renders_known_placeholders():
    prompt = _render_daily_report_prompt(
        template="# {title}\n\n{market_summary}\n\n{announcement_summary}\n\n{news_summary}\n\n{research_viewpoints}",
        title="晨会日报",
        topic="白酒行业今日重点",
        market_summary="- 市场波动收敛 [1]",
        announcement_summary="- 公司公告披露分红方案 [2]",
        news_summary="- 行业新闻提到需求恢复 [3]",
        research_viewpoints="- 券商观点偏积极 [4]",
        risks="- 渠道库存待验证",
        references="- [1] 市场日报 / chunk=1",
    )

    assert "晨会日报" in prompt
    assert "市场波动收敛" in prompt
    assert "券商观点偏积极" in prompt


def test_ingest_document_replaces_chunks_and_marks_parsed(monkeypatch, tmp_path):
    doc_path = tmp_path / "sample.md"
    doc_path.write_text("placeholder", encoding="utf-8")
    conn = FakeConnection(
        rows=[
            {"id": "doc-1", "file_path": str(doc_path), "parse_status": "pending"},
            {"id": "doc-1"},
            {"id": "chunk-row-1"},
            {"id": "chunk-row-2"},
            {"id": "doc-1"},
        ]
    )

    monkeypatch.setattr(documents_service, "read_document_text", lambda path: "第一段内容\n\n第二段内容")
    monkeypatch.setattr(documents_service, "split_chunks", lambda text, chunk_size, chunk_overlap: ["第一段内容", "第二段内容"])
    monkeypatch.setattr(documents_service, "estimate_tokens", lambda text: len(text))
    monkeypatch.setattr(documents_service, "embed_text", lambda text: [0.1, 0.2])
    monkeypatch.setattr(documents_service, "vector_literal", lambda vector: "[0.10000000,0.20000000]")

    result = documents_service.ingest_document(conn, "doc-1", chunk_size=32, chunk_overlap=8)

    assert result == {"document_id": "doc-1", "status": "parsed", "chunk_count": 2}
    executed_sql = [sql for sql, _ in conn.cursor_obj.executed]
    assert any("UPDATE documents SET parse_status = 'processing'" in sql for sql in executed_sql)
    assert any("DELETE FROM document_chunks WHERE document_id = %s" in sql for sql in executed_sql)
    assert sum("INSERT INTO document_chunks" in sql for sql in executed_sql) == 2
    assert any("SET parse_status = 'parsed'" in sql for sql in executed_sql)


def test_ingest_document_marks_failed_when_parser_raises(monkeypatch, tmp_path):
    doc_path = tmp_path / "sample.md"
    doc_path.write_text("placeholder", encoding="utf-8")
    conn = FakeConnection(
        rows=[
            {"id": "doc-1", "file_path": str(doc_path), "parse_status": "pending"},
            {"id": "doc-1"},
            {"id": "doc-1"},
        ]
    )

    monkeypatch.setattr(documents_service, "read_document_text", lambda path: (_ for _ in ()).throw(RuntimeError("bad pdf")))

    try:
        documents_service.ingest_document(conn, "doc-1")
    except AppError as exc:
        assert exc.message == "document parse failed"
    else:
        raise AssertionError("ingest_document should wrap parser failure")

    failure_sql = [sql for sql, _ in conn.cursor_obj.executed if "SET parse_status = 'failed'" in sql]
    assert len(failure_sql) == 1


def test_hybrid_search_orders_by_weighted_score_and_short_text_penalty(monkeypatch):
    rows = [[
        {"chunk_id": "c2", "chunk_text": "更长的高分段落", "score": 0.81, "vector_score": 0.82, "keyword_score": 0.8},
        {"chunk_id": "c1", "chunk_text": "短句", "score": 0.22, "vector_score": 0.9, "keyword_score": 0.88},
    ]]
    conn = FakeConnection(rows=rows)

    monkeypatch.setattr("app.services.search.embed_text", lambda query: [0.1, 0.2])
    monkeypatch.setattr("app.services.search.vector_literal", lambda vector: "[0.10000000,0.20000000]")
    monkeypatch.setattr("app.services.search.embedding_provider", lambda: "local_hash")

    result = hybrid_search(conn, "渠道库存", top_k=2, company_code="600519", doc_type="report")

    assert [item["chunk_id"] for item in result["items"]] == ["c2", "c1"]
    sql, params = conn.cursor_obj.executed[0]
    assert "0.45 * keyword_score + 0.55 * vector_score" in sql
    assert "char_length(chunk_text) < 30" in sql
    assert params[2:4] == ("600519", "report")


def test_answer_question_persists_citations_before_generation(monkeypatch):
    conn = object()
    saved = [{"citation_id": "cit-1", "chunk_text": "证据", "document_id": "doc-1", "chunk_id": "c1"}]
    state = {"saved": False}

    monkeypatch.setattr(
        "app.services.search.hybrid_search",
        lambda conn, question, top_k, company_code: {"embedding_provider": "local_hash", "items": [{"chunk_id": "c1"}]},
    )

    def fake_save_citations(conn, citations, task_id=None, asset_id=None):
        state["saved"] = True
        return saved

    def fake_generate_answer(question, citations, conn=None):
        assert state["saved"] is True
        assert citations == saved
        return "答案", "fallback"

    monkeypatch.setattr("app.services.search.save_citations", fake_save_citations)
    monkeypatch.setattr("app.services.search.generate_answer", fake_generate_answer)

    result = answer_question(conn, "收入增长原因？", task_id="task-1", asset_id="asset-1")

    assert result["citations"] == saved
    assert result["answer"] == "答案"
    assert result["embedding_provider"] == "local_hash"


def test_save_citations_rewrites_existing_rows_and_numbers_consistently():
    conn = FakeConnection(rows=[{"id": "cit-1"}, {"id": "cit-2"}])

    result = save_citations(
        conn,
        [
            {"document_id": "doc-1", "chunk_id": "c1", "chunk_text": "A", "score": 0.9},
            {"document_id": "doc-1", "chunk_id": "c2", "chunk_text": "B", "score": 0.8},
        ],
        task_id="task-1",
        asset_id="asset-1",
    )

    assert [item["citation_no"] for item in result] == [1, 2]
    assert [item["citation_id"] for item in result] == ["cit-1", "cit-2"]
    delete_sql, delete_params = conn.cursor_obj.executed[0]
    assert "DELETE FROM citations WHERE task_id = %s AND asset_id = %s" in delete_sql
    assert delete_params == ("task-1", "asset-1")


def test_execute_qa_task_updates_task_and_run_lifecycle(monkeypatch):
    conn = object()
    calls = []

    monkeypatch.setattr("app.services.search.get_task", lambda conn, task_id: {"id": task_id, "task_type": "qa"})
    monkeypatch.setattr("app.services.search.start_task", lambda conn, task_id: calls.append(("start", task_id)))
    monkeypatch.setattr(
        "app.services.search.answer_question",
        lambda conn, question, top_k, company_code, task_id, asset_id: {
            "answer": "结论",
            "answer_provider": "fallback",
            "embedding_provider": "local_hash",
            "citations": [{"citation_id": "cit-1"}],
        },
    )
    monkeypatch.setattr("app.services.search.create_task_run", lambda conn, task_id, **kwargs: calls.append(("run", task_id, kwargs)))
    monkeypatch.setattr(
        "app.services.search.complete_task",
        lambda conn, task_id, output_payload, result_summary: {
            "id": task_id,
            "status": "completed",
            "task_type": "qa",
            "started_at": "s",
            "finished_at": "f",
        },
    )

    result = execute_qa_task(conn, "问题", task_id="task-1")

    assert result["task"]["status"] == "completed"
    assert calls[0] == ("start", "task-1")
    assert calls[1][0] == "run"
    assert calls[1][2]["status"] == "completed"
    assert calls[1][2]["output_payload"]["citations_count"] == 1


def test_stream_answer_question_updates_task_and_run_lifecycle(monkeypatch):
    conn = object()
    calls = []

    monkeypatch.setattr("app.services.search.create_qa_task", lambda conn, question, top_k, company_code, request_id=None: {"id": "task-1"})
    monkeypatch.setattr("app.services.search.start_task", lambda conn, task_id: calls.append(("start", task_id)))
    monkeypatch.setattr(
        "app.services.search.hybrid_search",
        lambda conn, question, top_k, company_code: {"embedding_provider": "local_hash", "items": [{"chunk_id": "c1"}]},
    )
    monkeypatch.setattr(
        "app.services.search.save_citations",
        lambda conn, citations, task_id=None, asset_id=None: [{"citation_id": "cit-1", "chunk_id": "c1"}],
    )
    monkeypatch.setattr(
        "app.services.search.generate_answer_stream",
        lambda question, citations, conn=None: (iter(["结论", "补充"]), "llm"),
    )
    monkeypatch.setattr("app.services.search.create_task_run", lambda conn, task_id, **kwargs: calls.append(("run", task_id, kwargs)))
    monkeypatch.setattr(
        "app.services.search.complete_task",
        lambda conn, task_id, output_payload, result_summary: calls.append(("complete", task_id, output_payload, result_summary)),
    )

    result = stream_answer_question(conn, "问题", top_k=3, request_id="req-1")
    chunks = list(result["answer_stream"])

    assert chunks == ["结论", "补充"]
    assert result["task_id"] == "task-1"
    assert calls[0] == ("start", "task-1")
    assert calls[1][0] == "run"
    assert calls[1][2]["status"] == "completed"
    assert calls[1][2]["run_name"] == "qa.ask.stream"
    assert calls[2][0] == "complete"
    assert calls[2][2]["answer"] == "结论补充"


def test_stream_answer_question_marks_failed_run_on_stream_error(monkeypatch):
    conn = object()
    calls = []

    monkeypatch.setattr("app.services.search.create_qa_task", lambda conn, question, top_k, company_code, request_id=None: {"id": "task-1"})
    monkeypatch.setattr("app.services.search.start_task", lambda conn, task_id: None)
    monkeypatch.setattr(
        "app.services.search.hybrid_search",
        lambda conn, question, top_k, company_code: {"embedding_provider": "local_hash", "items": [{"chunk_id": "c1"}]},
    )
    monkeypatch.setattr(
        "app.services.search.save_citations",
        lambda conn, citations, task_id=None, asset_id=None: [{"citation_id": "cit-1", "chunk_id": "c1"}],
    )

    def broken_stream():
        yield "结论"
        raise RuntimeError("stream broken")

    monkeypatch.setattr(
        "app.services.search.generate_answer_stream",
        lambda question, citations, conn=None: (broken_stream(), "llm"),
    )
    monkeypatch.setattr("app.services.search.fail_task", lambda conn, task_id, error_message: calls.append(("fail", task_id, error_message)))
    monkeypatch.setattr("app.services.search.create_task_run", lambda conn, task_id, **kwargs: calls.append(("run", task_id, kwargs)))

    result = stream_answer_question(conn, "问题", top_k=3, request_id="req-1")

    try:
        list(result["answer_stream"])
    except RuntimeError as exc:
        assert str(exc) == "stream broken"
    else:
        raise AssertionError("expected stream failure to surface")

    assert calls[0] == ("fail", "task-1", "stream broken")
    assert calls[1][0] == "run"
    assert calls[1][2]["status"] == "failed"
    assert calls[1][2]["run_name"] == "qa.ask.stream"


def test_execute_task_marks_failure_and_records_failed_run(monkeypatch):
    conn = object()
    calls = []

    monkeypatch.setattr(
        "app.services.tasks.get_task",
        lambda conn, task_id: {
            "id": task_id,
            "task_type": "qa",
            "input_text": "问题",
            "input_payload": {"question": "问题"},
            "task_title": "问题",
            "route_agent": "qa",
            "priority": "normal",
        },
    )
    monkeypatch.setattr("app.services.tasks.start_task", lambda conn, task_id: calls.append(("start", task_id)))
    monkeypatch.setattr("app.services.tasks.create_task_run", lambda conn, task_id, **kwargs: calls.append(("run", task_id, kwargs)))
    monkeypatch.setattr("app.services.tasks.fail_task", lambda conn, task_id, error: calls.append(("fail", task_id, error)))
    monkeypatch.setattr("app.agents.supervisor.route_task", lambda conn, payload, request_id=None: (_ for _ in ()).throw(RuntimeError("route failed")))

    try:
        execute_task(conn, "task-1")
    except RuntimeError as exc:
        assert str(exc) == "route failed"
    else:
        raise AssertionError("execute_task should re-raise route failure")

    assert calls[0] == ("start", "task-1")
    assert calls[1][2]["status"] == "running"
    assert calls[2] == ("fail", "task-1", "route failed")
    assert calls[3][2]["status"] == "failed"


def test_create_asset_assigns_root_revision_sources_and_tags(monkeypatch):
    conn = FakeConnection(rows=[{"id": "asset-1", "content_markdown": "# 标题", "summary": "摘要"}, {"id": "asset-1", "content_markdown": "# 标题", "summary": "摘要"}])
    calls = {"sources": None, "tags": None}

    monkeypatch.setattr(assets_service, "get_asset", lambda conn, asset_id: {"id": asset_id, "sources": [{"id": "src-1"}], "tags": [{"id": "tag-1"}]})
    monkeypatch.setattr(assets_service, "_replace_asset_sources", lambda cur, asset_id, sources: calls.__setitem__("sources", (asset_id, sources)))
    monkeypatch.setattr(assets_service, "_replace_asset_tags", lambda cur, asset_id, tag_ids: calls.__setitem__("tags", (asset_id, tag_ids)))

    result = assets_service.create_asset(
        conn,
        {
            "asset_type": "memo",
            "title": "资产",
            "content_markdown": "# 标题",
            "summary": "摘要",
            "parent_asset_id": "parent-1",
            "sources": [{"source_type": "citation", "source_ref_id": "cit-1"}],
            "tag_ids": ["tag-1", "tag-2"],
        },
    )

    assert result["id"] == "asset-1"
    executed_sql = [sql for sql, _ in conn.cursor_obj.executed]
    assert any("INSERT INTO research_assets" in sql for sql in executed_sql)
    assert any("SET root_asset_id = COALESCE" in sql for sql in executed_sql)
    assert any("INSERT INTO asset_revisions" in sql for sql in executed_sql)
    assert calls["sources"] == ("asset-1", [{"source_type": "citation", "source_ref_id": "cit-1"}])
    assert calls["tags"] == ("asset-1", ["tag-1", "tag-2"])


def test_update_asset_increments_version_and_replaces_relations(monkeypatch):
    conn = FakeConnection(rows=[{"content_markdown": "# v2", "summary": "新版摘要"}])
    calls = {"sources": None, "tags": None}

    monkeypatch.setattr(
        assets_service,
        "get_asset",
        lambda conn, asset_id: {"id": asset_id, "version": 2, "sources": [], "tags": []} if asset_id == "asset-1" else {"id": asset_id},
    )
    monkeypatch.setattr(assets_service, "_replace_asset_sources", lambda cur, asset_id, sources: calls.__setitem__("sources", (asset_id, sources)))
    monkeypatch.setattr(assets_service, "_replace_asset_tags", lambda cur, asset_id, tag_ids: calls.__setitem__("tags", (asset_id, tag_ids)))

    result = assets_service.update_asset(
        conn,
        "asset-1",
        {
            "content_markdown": "# v2",
            "summary": "新版摘要",
            "change_note": "补充数据源",
            "sources": [{"source_type": "document", "source_ref_id": "doc-1"}],
            "tag_ids": ["tag-9"],
        },
    )

    assert result["id"] == "asset-1"
    update_sql = [sql for sql, _ in conn.cursor_obj.executed if "UPDATE research_assets" in sql][0]
    assert "version = %s" in update_sql
    revision_sql = [sql for sql, _ in conn.cursor_obj.executed if "INSERT INTO asset_revisions" in sql]
    assert len(revision_sql) == 1
    assert calls["sources"] == ("asset-1", [{"source_type": "document", "source_ref_id": "doc-1"}])
    assert calls["tags"] == ("asset-1", ["tag-9"])


def test_route_task_uses_orchestrator_default_agent(monkeypatch):
    class StubAgent:
        def __init__(self):
            self.received = None

        def run(self, conn, context):
            self.received = context
            return {"decision": {"agent": "research_agent"}, "result": {"ok": True}}

    stub = StubAgent()
    monkeypatch.setattr("app.agents.supervisor.default_agent_registry.default", lambda: stub)

    result = route_task(object(), {"task_type": "qa", "question": "茅台为什么涨价？"}, request_id="req-9")

    assert result["result"]["ok"] is True
    assert stub.received.request_id == "req-9"
    assert stub.received.payload["question"] == "茅台为什么涨价？"


def test_research_agent_routes_summary_to_summary_skill(monkeypatch):
    captured = {}

    def fake_run(conn, skill_call):
        captured["name"] = skill_call.name
        captured["payload"] = skill_call.payload
        return type("SkillResult", (), {"data": {"summary": "ok"}})()

    monkeypatch.setattr("app.agents.research_agent.default_registry.run", fake_run)

    result = ResearchAgent().run(
        object(),
        AgentContext(payload={"task_type": "summary", "topic": "白酒行业"}),
    )

    assert result["skill"] == "research.summary"
    assert captured["name"] == "research.summary"
    assert captured["payload"]["topic"] == "白酒行业"


def test_reporting_agent_routes_weekly_report_and_exports(monkeypatch):
    captured = {}

    def fake_run(conn, skill_call):
        captured["name"] = skill_call.name
        return type(
            "SkillResult",
            (),
            {
                "data": {
                    "asset": {"id": "asset-1"},
                    "content_markdown": "# 周报",
                    "citations": [],
                    "prompt_template_used": True,
                    "template_key": "report.weekly.custom",
                }
            },
        )()

    monkeypatch.setattr("app.agents.reporting_agent.default_registry.run", fake_run)
    monkeypatch.setattr("app.agents.reporting_agent.export_asset", lambda conn, asset_id, export_format: {"asset_id": asset_id, "format": export_format})

    result = ReportingAgent().run(
        object(),
        AgentContext(payload={"task_type": "weekly_report", "topic": "白酒周报", "export_format": "docx"}),
    )

    assert result["skill"] == "report.weekly"
    assert result["result"]["export"]["format"] == "docx"
    assert captured["name"] == "report.weekly"
