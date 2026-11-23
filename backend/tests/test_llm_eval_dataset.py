import json
from pathlib import Path

import pytest

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
        "qwen3:8b",
        "llava:7b",
        "phi:2.7b",
    ]


@pytest.mark.parametrize(
    ("model", "expect_thinking_disabled"),
    [("qwen3:4b", True), ("qwen3:8b", True), ("gemma3:4b", False)],
)
def test_benchmark_disables_qwen3_thinking_only(monkeypatch, model, expect_thinking_disabled):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"message":{"content":"answer"}}'

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(benchmark_llm, "urlopen", fake_urlopen)
    benchmark_llm.request_chat(
        "http://localhost:11434",
        model,
        [{"role": "user", "content": "Bonjour."}],
    )

    assert ("think" in captured["payload"]) is expect_thinking_disabled
    if expect_thinking_disabled:
        assert captured["payload"]["think"] is False


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
