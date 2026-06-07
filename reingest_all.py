"""
Re-ingest all documents with real embeddings (bge-m3 via local Ollama).
Run: python reingest_all.py
"""
import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "app"))

# Install deps if needed
try:
    import psycopg
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "psycopg"], check=True)
    import psycopg

try:
    from app.services.embeddings import embed_text, vector_literal
    from app.core.config import get_settings
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're in the project root directory")
    sys.exit(1)


def reingest_all():
    settings = get_settings()
    print(f"Embedding provider: {settings.embedding_provider}")
    print(f"Embedding model: {settings.embedding_model}")
    print(f"Embedding dim: {settings.embedding_dim}")
    print()

    # Connect to DB
    db_url = settings.database_url
    print(f"Connecting to DB: {db_url}")
    conn = psycopg.connect(db_url)
    cur = conn.cursor()

    # Get all documents with status='parsed'
    cur.execute(
        "SELECT id, title, parse_status FROM documents WHERE deleted_at IS NULL ORDER BY created_at"
    )
    docs = cur.fetchall()
    print(f"Found {len(docs)} documents")
    print()

    total_chunks = 0
    total_updated = 0

    for doc in docs:
        doc_id, title, parse_status = doc
        print(f"Document: {doc_id} - {title} (status={parse_status})")

        # Get chunks for this document
        cur.execute(
            "SELECT id, chunk_index, chunk_text FROM document_chunks "
            "WHERE document_id = %s ORDER BY chunk_index",
            (doc_id,)
        )
        chunks = cur.fetchall()
        print(f"  Chunks: {len(chunks)}")

        if not chunks:
            print("  SKIP: no chunks")
            print()
            continue

        updated = 0
        for chunk_id, chunk_index, chunk_text in chunks:
            try:
                embedding = embed_text(chunk_text)
                embedding_str = vector_literal(embedding)
                cur.execute(
                    "UPDATE document_chunks SET embedding = %s::vector, embedding_model = %s "
                    "WHERE id = %s",
                    (embedding_str, settings.embedding_model, chunk_id)
                )
                updated += 1
                if updated % 5 == 0:
                    print(f"  Progress: {updated}/{len(chunks)} chunks updated...")
            except Exception as e:
                print(f"  ERROR chunk {chunk_index}: {e}")
                continue

        conn.commit()
        total_chunks += len(chunks)
        total_updated += updated
        print(f"  DONE: {updated}/{len(chunks)} chunks updated")
        print()

    cur.close()
    conn.close()

    print(f"=== Summary ===")
    print(f"Total documents: {len(docs)}")
    print(f"Total chunks: {total_chunks}")
    print(f"Total updated: {total_updated}")


if __name__ == "__main__":
    reingest_all()
