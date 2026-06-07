from psycopg import Connection


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
