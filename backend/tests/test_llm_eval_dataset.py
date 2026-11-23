import json
from pathlib import Path

from scripts import benchmark_llm


BACKEND_DIR = Path(__file__).resolve().parents[1]
DATASET_PATH = BACKEND_DIR / "data" / "llm_eval" / "prompts.json"


def test_llm_evaluation_dataset_has_valid_multilingual_cases():
    cases = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    ids = [case["id"] for case in cases]

    assert len(cases) >= 30
    assert len(ids) == len(set(ids))
    assert {"fr", "tn-arabic", "arabizi", "mixed"} <= {case["language"] for case in cases}
    assert {"orientation", "admission", "multi_turn", "grounding"} <= {
        case["category"] for case in cases
    }

    for case in cases:
        assert case["messages"][-1]["role"] == "user"
        assert case["checks"]
        assert all(message["role"] in {"user", "assistant"} for message in case["messages"])


def test_benchmark_default_models_include_installed_candidates():
    assert benchmark_llm.DEFAULT_MODELS == [
        "gemma3:4b",
        "qwen3:4b",
        "minicpm-v:latest",
        "mistral:latest",
    ]


def test_benchmark_runs_the_same_cases_for_each_model(monkeypatch):
    def fake_request_chat(_base_url, model, _messages):
        return {
            "message": {"content": f"Answer from {model}"},
            "eval_count": 10,
            "eval_duration": 2_000_000_000,
        }, 12.5

    monkeypatch.setattr(benchmark_llm, "request_chat", fake_request_chat)
    report = benchmark_llm.run_benchmark(
        ["gemma3:4b", "qwen3:4b"],
        "http://localhost:11434",
        warmup=True,
    )

    assert report["case_count"] >= 30
    assert len(report["runs"]) == report["case_count"] * 2
    assert report["summary"]["gemma3:4b"]["success_count"] == report["case_count"]
    assert report["summary"]["qwen3:4b"]["mean_tokens_per_second"] == 5.0
    assert report["warmups"]["gemma3:4b"]["status"] == "ok"
