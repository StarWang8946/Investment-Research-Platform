"""
Re-ingest all documents with real embeddings (bge-m3 via local ollama).
Uses psql CLI to avoid psycopg binary issues.
Run: python reingest_all_v2.py
"""
import subprocess, json, sys, os, time

OLLAMA_MODEL = "bge-m3"
DB_URL = "postgresql://localhost:5432/investment_research_mvp"
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def run_ollama_embed(text):
    """Call ollama run bge-m3 via subprocess."""
    result = subprocess.run(
        ["ollama", "run", OLLAMA_MODEL, text],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"ollama failed: {result.stderr[:200]}")
    return json.loads(result.stdout.strip())


def run_psql(sql, dbname="investment_research_mvp"):
    """Run SQL via psql and return stdout."""
    result = subprocess.run(
        ["psql", "-h", "localhost", "-p", "5432",
         "-U", "wangjiaxing", "-d", dbname, "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql failed: {result.stderr}")
    return result.stdout


def get_docs():
    """Get all documents from DB via psql."""
    sql = (
        "SELECT id, title, parse_status "
        "FROM documents WHERE deleted_at IS NULL ORDER BY created_at;"
    )
    stdout = run_psql(sql)
    lines = [l for l in stdout.strip().split("\n") if l.strip()]
    docs = []
    for line in lines:
        parts = line.strip().split("|")
        if len(parts) >= 3:
            docs.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
        elif len(parts) == 2:
            docs.append((parts[0].strip(), parts[1].strip(), ""))
    return docs


def get_chunks(doc_id):
    """Get chunks for a document."""
    sql = (
        f"SELECT id, chunk_index, chunk_text "
        f"FROM document_chunks WHERE document_id = '{doc_id}' "
        f"ORDER BY chunk_index;"
    )
    stdout = run_psql(sql)
    lines = [l for l in stdout.strip().split("\n") if l.strip()]
    chunks = []
    for line in lines:
        parts = line.strip().split("|")
        if len(parts) >= 3:
            chunks.append((parts[0].strip(), int(parts[1].strip()), parts[2].strip()))
    return chunks


def update_chunk_embedding(chunk_id, embedding, model_name):
    """Update a chunk's embedding via psql."""
    # Format embedding as pgvector literal
    emb_str = "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"
    # Escape single quotes in emb_str for SQL
    emb_escaped = emb_str.replace("'", "''")
    sql = (
        f"UPDATE document_chunks "
        f"SET embedding = '{emb_escaped}'::vector, "
        f"embedding_model = '{model_name}' "
        f"WHERE id = '{chunk_id}';"
    )
    run_psql(sql)


def reingest_all():
    print(f"Re-ingesting all documents with {OLLAMA_MODEL} embeddings...")
    print()

    docs = get_docs()
    print(f"Found {len(docs)} documents")
    print()

    total_chunks = 0
    total_updated = 0

    for doc_id, title, parse_status in docs:
        print(f"Document: {doc_id} - {title} (status={parse_status})")

        chunks = get_chunks(doc_id)
        print(f"  Chunks: {len(chunks)}")

        if not chunks:
            print("  SKIP: no chunks")
            print()
            continue

        updated = 0
        for chunk_id, chunk_index, chunk_text in chunks:
            try:
                t0 = time.time()
                embedding = run_ollama_embed(chunk_text)
                elapsed = round(time.time() - t0, 2)
                update_chunk_embedding(chunk_id, embedding, OLLAMA_MODEL)
                updated += 1
                if updated % 3 == 0 or updated == len(chunks):
                    print(f"  [{updated}/{len(chunks)}] chunk {chunk_index} done ({elapsed}s)")
            except Exception as e:
                print(f"  ERROR chunk {chunk_index}: {e}")
                continue

        total_chunks += len(chunks)
        total_updated += updated
        print(f"  DONE: {updated}/{len(chunks)} chunks updated")
        print()

    print(f"=== Summary ===")
    print(f"Total documents: {len(docs)}")
    print(f"Total chunks: {total_chunks}")
    print(f"Total updated: {total_updated}")


if __name__ == "__main__":
    reingest_all()
