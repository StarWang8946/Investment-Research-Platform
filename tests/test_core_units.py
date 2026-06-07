from pydantic import ValidationError

from app.api.routers.documents import IngestRequest
from app.api.routers.qa import AskRequest
from app.api.routers.search import SearchRequest
from app.agents.base_agent import AgentTaskInput, AgentTaskOutput
from app.agents.orchestrator_agent import decide_route
from app.agents.registry import AgentRegistry
from app.agents.research_agent import ResearchAgent
from app.core.config import get_settings
from app.services.embeddings import embed_text, embedding_provider, vector_literal
from app.services.llm import generate_answer
from app.services.text import split_chunks


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


def test_llm_fallback_without_config(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()

    answer, provider = generate_answer("收入增长原因是什么？", [])

    assert provider == "fallback"
    assert "未检索到" in answer
    get_settings.cache_clear()


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
