from pathlib import Path

from scripts.eval_retrieval import load_cases, summarize


def test_retrieval_cases_are_loadable():
    cases = load_cases(Path("evals/retrieval_cases.jsonl"))

    assert len(cases) >= 3
    for case in cases:
        assert case["id"]
        assert case["query"]
        assert case["top_k"] >= 1
        assert case["expected_keywords"]


def test_retrieval_summary_counts_pass_rate():
    payload = summarize([{"passed": True}, {"passed": False}])

    assert payload["total"] == 2
    assert payload["passed"] == 1
    assert payload["failed"] == 1
    assert payload["pass_rate"] == 0.5
