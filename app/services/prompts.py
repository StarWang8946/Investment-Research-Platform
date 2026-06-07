from psycopg import Connection

DEFAULT_PROMPT_TEMPLATES = [
    {
        "template_key": "llm.system.default",
        "template_name": "默认 LLM System Prompt",
        "agent_name": "llm",
        "scenario": "system",
        "content": "你是严谨的中文投资研究助理。",
    },
    {
        "template_key": "research.qa.rag",
        "template_name": "投研问答 RAG Prompt",
        "agent_name": "research_agent",
        "scenario": "qa",
        "content": (
            "你是投资研究助理。请只基于给定资料回答问题，结论要简洁，并在关键句后标注引用编号。\n\n"
            "问题：{question}\n\n"
            "资料：\n{context}\n\n"
            "请输出：核心结论、依据、风险/待验证事项。"
        ),
    },
    {
        "template_key": "research.memo",
        "template_name": "投研备忘录生成 Prompt",
        "agent_name": "research_agent",
        "scenario": "memo",
        "content": (
            "请基于资料生成投研备忘录，突出核心结论、证据和风险，关键句必须带引用编号。\n\n"
            "主题：{topic}\n\n"
            "已有问答草稿：\n{qa_answer}\n\n"
            "多文档关键信息：\n{evidence}\n\n"
            "引用资料：\n{references}\n\n"
            "请输出 Markdown，保留标题层级，不要编造资料外的信息。"
        ),
    },
    {
        "template_key": "research.daily_report",
        "template_name": "晨会日报生成 Prompt",
        "agent_name": "research_agent",
        "scenario": "daily_report",
        "content": (
            "请基于以下资料生成晨会日报 Markdown，必须输出“市场概览、公告跟踪、新闻动态、研究观点、风险提示、引用”六个部分，关键句带引用编号。\n\n"
            "主题：{topic}\n\n"
            "市场概览候选：\n{market_summary}\n\n"
            "公告跟踪候选：\n{announcement_summary}\n\n"
            "新闻动态候选：\n{news_summary}\n\n"
            "研究观点候选：\n{research_viewpoints}\n\n"
            "风险提示：\n{risks}\n\n"
            "引用资料：\n{references}\n"
        ),
    },
    {
        "template_key": "research.weekly_report",
        "template_name": "研究周报生成 Prompt",
        "agent_name": "research_agent",
        "scenario": "weekly_report",
        "content": (
            "请基于资料生成研究周报，概括本周重点、关键进展和风险提示，关键句必须带引用编号。\n\n"
            "主题：{topic}\n\n"
            "已有问答草稿：\n{qa_answer}\n\n"
            "多文档关键信息：\n{evidence}\n\n"
            "引用资料：\n{references}\n\n"
            "请输出 Markdown，保留标题层级，不要编造资料外的信息。"
        ),
    },
    {
        "template_key": "research.investment_brief",
        "template_name": "投决材料生成 Prompt",
        "agent_name": "research_agent",
        "scenario": "investment_brief",
        "content": (
            "请基于资料生成投决材料，输出投决结论、核心依据、风险与待验证事项，关键句必须带引用编号。\n\n"
            "主题：{topic}\n\n"
            "已有问答草稿：\n{qa_answer}\n\n"
            "多文档关键信息：\n{evidence}\n\n"
            "引用资料：\n{references}\n\n"
            "请输出 Markdown，保留标题层级，不要编造资料外的信息。"
        ),
    },
    {
        "template_key": "research.summary",
        "template_name": "资料摘要生成 Prompt",
        "agent_name": "research_agent",
        "scenario": "summary",
        "content": (
            "请基于以下投研资料生成中文摘要，突出事实、变化、原因和待跟踪事项，关键句必须带引用编号。\n\n"
            "主题：{topic}\n\n"
            "资料：\n{context}\n\n"
            "请输出 Markdown，包含“摘要”和“待跟踪事项”。不要编造资料外的信息。"
        ),
    },
    {
        "template_key": "research.conclusion",
        "template_name": "研究结论生成 Prompt",
        "agent_name": "research_agent",
        "scenario": "conclusion",
        "content": (
            "请基于投研资料形成可执行的研究结论，区分结论、依据、风险和待验证事项，关键句必须带引用编号。\n\n"
            "主题：{topic}\n\n"
            "问答草稿：\n{qa_answer}\n\n"
            "引用资料：\n{references}\n\n"
            "请输出 Markdown，不要编造资料外的信息。"
        ),
    },
]


def list_prompts(conn: Connection, agent_name: str | None = None, scenario: str | None = None, status: str | None = None) -> dict:
    where = ["1=1"]
    params: list = []
    for field, value in (("agent_name", agent_name), ("scenario", scenario), ("status", status)):
        if value:
            where.append(f"{field} = %s")
            params.append(value)
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM prompt_templates WHERE {' AND '.join(where)} ORDER BY template_key", tuple(params))
        rows = cur.fetchall()
    return {"items": [dict(row) for row in rows]}


def get_prompt_by_key(conn: Connection, template_key: str, status: str | None = "active") -> dict | None:
    where = ["template_key = %s"]
    params: list = [template_key]
    if status:
        where.append("status = %s")
        params.append(status)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT * FROM prompt_templates WHERE {' AND '.join(where)} ORDER BY version DESC LIMIT 1",
            tuple(params),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_prompt_content(conn: Connection, template_key: str) -> str | None:
    template = get_prompt_by_key(conn, template_key)
    return template["content"] if template else None


def get_default_prompt_content(template_key: str) -> str:
    for template in DEFAULT_PROMPT_TEMPLATES:
        if template["template_key"] == template_key:
            return template["content"]
    raise KeyError(template_key)


def render_prompt_template(template: str, values: dict[str, str]) -> str:
    try:
        return template.format(**values)
    except KeyError:
        return template


def create_prompt(conn: Connection, payload: dict) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO prompt_templates (template_key, template_name, agent_name, scenario, content, version, status)
            VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, 'active'))
            RETURNING *
            """,
            (
                payload["template_key"], payload["template_name"], payload.get("agent_name"),
                payload.get("scenario"), payload["content"], payload.get("version", 1),
                payload.get("status"),
            ),
        )
        return dict(cur.fetchone())


def update_prompt(conn: Connection, template_key: str, payload: dict) -> dict | None:
    allowed_fields = ("template_name", "agent_name", "scenario", "content", "version", "status")
    assignments = []
    params: list = []
    for field in allowed_fields:
        if field in payload:
            assignments.append(f"{field} = %s")
            params.append(payload[field])
    if not assignments:
        return get_prompt_by_key(conn, template_key, status=None)

    assignments.append("updated_at = NOW()")
    params.append(template_key)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE prompt_templates
            SET {', '.join(assignments)}
            WHERE template_key = %s
            RETURNING *
            """,
            tuple(params),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def seed_default_prompts(conn: Connection) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for template in DEFAULT_PROMPT_TEMPLATES:
            cur.execute(
                """
                INSERT INTO prompt_templates (template_key, template_name, agent_name, scenario, content, version, status)
                VALUES (%s, %s, %s, %s, %s, 1, 'active')
                ON CONFLICT (template_key) DO NOTHING
                RETURNING id
                """,
                (
                    template["template_key"],
                    template["template_name"],
                    template["agent_name"],
                    template["scenario"],
                    template["content"],
                ),
            )
            if cur.fetchone():
                inserted += 1
    return inserted
