from time import perf_counter

from psycopg import Connection

from app.core.exceptions import AppError
from app.services.embeddings import embed_text, embedding_provider, vector_literal
from app.services.llm import generate_answer
from app.services.tasks import complete_task, create_qa_task, create_task_run, fail_task, get_task, start_task


def hybrid_search(conn: Connection, query: str, top_k: int = 10, company_code: str | None = None, doc_type: str | None = None) -> dict:
    where = ["d.deleted_at IS NULL", "d.parse_status = 'parsed'"]
    filter_params: list = []
    if company_code:
        where.append("d.company_code = %s")
        filter_params.append(company_code)
    if doc_type:
        where.append("d.doc_type = %s")
        filter_params.append(doc_type)
    query_vector = vector_literal(embed_text(query))
    params = [query, query_vector] + filter_params + [query, query, top_k]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            WITH scored AS (
                SELECT dc.id AS chunk_id, dc.document_id, dc.chunk_index, dc.chunk_text,
                       dc.page_no, dc.position_start, dc.position_end,
                       d.title, d.source_id, d.company_code, d.company_name,
                       similarity(dc.chunk_text, %s) AS keyword_score,
                       CASE
                           WHEN dc.embedding IS NULL THEN 0.0
                           ELSE 1 - (dc.embedding <=> %s::vector)
                       END AS vector_score
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE {' AND '.join(where)}
                  AND (
                      dc.chunk_text ILIKE '%%' || %s || '%%'
                      OR similarity(dc.chunk_text, %s) > 0.02
                      OR dc.embedding IS NOT NULL
                  )
            )
            SELECT *,
                   (0.45 * keyword_score + 0.55 * vector_score)
                   * CASE WHEN char_length(chunk_text) < 30 THEN 0.35 ELSE 1.0 END AS score
            FROM scored
            ORDER BY score DESC, vector_score DESC, keyword_score DESC, chunk_index ASC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cur.fetchall()
    return {"query": query, "embedding_provider": embedding_provider(), "items": [dict(row) for row in rows]}


def save_citations(conn: Connection, citations: list[dict], task_id: str | None = None, asset_id: str | None = None) -> list[dict]:
    if not citations or not (task_id or asset_id):
        return citations
    saved = []
    with conn.cursor() as cur:
        if task_id and asset_id:
            cur.execute("DELETE FROM citations WHERE task_id = %s AND asset_id = %s", (task_id, asset_id))
        elif task_id:
            cur.execute("DELETE FROM citations WHERE task_id = %s", (task_id,))
        elif asset_id:
            cur.execute("DELETE FROM citations WHERE asset_id = %s", (asset_id,))
        for index, item in enumerate(citations, start=1):
            cur.execute(
                """
                INSERT INTO citations (
                    task_id, asset_id, document_id, chunk_id, citation_no, source_id,
                    page_no, position_start, position_end, quote_text, rank, relevance_score
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    task_id,
                    asset_id,
                    item["document_id"],
                    item["chunk_id"],
                    index,
                    item.get("source_id") or str(item["document_id"]),
                    item.get("page_no"),
                    item.get("position_start"),
                    item.get("position_end"),
                    (item.get("chunk_text") or "")[:500],
                    index,
                    item.get("score"),
                ),
            )
            row = cur.fetchone()
            saved_item = dict(item)
            saved_item["citation_id"] = row["id"]
            saved_item["citation_no"] = index
            saved.append(saved_item)
    return saved


def execute_qa_task(
    conn: Connection,
    question: str,
    top_k: int = 5,
    company_code: str | None = None,
    task_id: str | None = None,
    asset_id: str | None = None,
    request_id: str | None = None,
) -> dict:
    if task_id:
        task = get_task(conn, task_id)
        if task["task_type"] != "qa":
            raise AppError(4002, "task type mismatch for qa execution", 400)
    else:
        task = create_qa_task(conn, question, top_k, company_code, request_id=request_id)

    task_id = str(task["id"])
    started = perf_counter()
    start_task(conn, task_id)
    try:
        result = answer_question(
            conn,
            question,
            top_k=top_k,
            company_code=company_code,
            task_id=task_id,
            asset_id=asset_id,
        )
        duration_ms = int((perf_counter() - started) * 1000)
        run_output = {
            "answer_provider": result["answer_provider"],
            "embedding_provider": result["embedding_provider"],
            "citations_count": len(result["citations"]),
        }
        create_task_run(
            conn,
            task_id,
            run_type="qa",
            run_name="qa.ask",
            input_payload={"question": question, "top_k": top_k, "company_code": company_code},
            output_payload=run_output,
            status="completed",
            duration_ms=duration_ms,
        )
        task = complete_task(
            conn,
            task_id,
            output_payload={
                **run_output,
                "question": question,
                "answer": result["answer"],
                "citation_ids": [str(item["citation_id"]) for item in result["citations"] if item.get("citation_id")],
            },
            result_summary=result["answer"][:1000],
        )
        result["task"] = {
            "id": task["id"],
            "status": task["status"],
            "task_type": task["task_type"],
            "started_at": task["started_at"],
            "finished_at": task["finished_at"],
        }
        return result
    except Exception as exc:
        duration_ms = int((perf_counter() - started) * 1000)
        fail_task(conn, task_id, str(exc))
        create_task_run(
            conn,
            task_id,
            run_type="qa",
            run_name="qa.ask",
            input_payload={"question": question, "top_k": top_k, "company_code": company_code},
            status="failed",
            duration_ms=duration_ms,
            error_message=str(exc),
        )
        raise


def answer_question(
    conn: Connection,
    question: str,
    top_k: int = 5,
    company_code: str | None = None,
    task_id: str | None = None,
    asset_id: str | None = None,
) -> dict:
    results = hybrid_search(conn, question, top_k, company_code)
    citations = save_citations(conn, results["items"], task_id=task_id, asset_id=asset_id)
    answer, answer_provider = generate_answer(question, citations)
    return {
        "question": question,
        "answer": answer,
        "answer_provider": answer_provider,
        "embedding_provider": results["embedding_provider"],
        "citations": citations,
    }
