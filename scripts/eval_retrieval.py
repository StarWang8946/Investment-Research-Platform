from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import psycopg
from psycopg.rows import dict_row

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import get_settings
from app.services.search import hybrid_search


DEFAULT_CASES = ROOT_DIR / "evals" / "retrieval_cases.jsonl"


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            case.setdefault("id", f"case_{line_no}")
            case.setdefault("top_k", 5)
            case.setdefault("expected_keywords", [])
            cases.append(case)
    return cases


def evaluate_case(conn: psycopg.Connection, case: dict[str, Any]) -> dict[str, Any]:
    result = hybrid_search(
        conn,
        case["query"],
        top_k=case.get("top_k", 5),
        company_code=case.get("company_code"),
        doc_type=case.get("doc_type"),
    )
    items = result["items"]
    joined_text = "\n".join((item.get("chunk_text") or "") for item in items)
    expected_keywords = case.get("expected_keywords", [])
    matched_keywords = [keyword for keyword in expected_keywords if keyword in joined_text]
    passed = bool(items) and len(matched_keywords) == len(expected_keywords)
    return {
        "id": case["id"],
        "query": case["query"],
        "passed": passed,
        "hit_count": len(items),
        "expected_keywords": expected_keywords,
        "matched_keywords": matched_keywords,
        "missing_keywords": [keyword for keyword in expected_keywords if keyword not in matched_keywords],
        "top_hits": [
            {
                "rank": index,
                "document_id": str(item.get("document_id")),
                "chunk_id": str(item.get("chunk_id")),
                "title": item.get("title"),
                "score": float(item.get("score") or 0),
                "snippet": " ".join((item.get("chunk_text") or "").split())[:180],
            }
            for index, item in enumerate(items[:3], start=1)
        ],
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for item in results if item["passed"])
    total = len(results)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality against JSONL cases.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="Path to retrieval JSONL cases.")
    parser.add_argument("--output", type=Path, default=None, help="Optional path to write JSON results.")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    with psycopg.connect(get_settings().database_url, row_factory=dict_row) as conn:
        results = [evaluate_case(conn, case) for case in cases]
    payload = summarize(results)

    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    if payload["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
