#!/usr/bin/env python3
"""Run the SmartCampus prompt set against Ollama models and save reviewable results."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.agents.prompts import SYSTEM_PROMPT  # noqa: E402

DATASET_PATH = BACKEND_DIR / "data" / "llm_eval" / "prompts.json"
DEFAULT_MODELS = [
    "gemma3:4b",
    "qwen3:4b",
    "minicpm-v:latest",
    "mistral:latest",
]
TIMEOUT_SECONDS = 180
TEMPERATURE = 0.2
TOP_P = 0.9
MAX_TOKENS = 500


class OllamaRequestError(Exception):
    pass


def request_chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
) -> tuple[dict, float]:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "num_predict": MAX_TOKENS,
        },
    }
    request = Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OllamaRequestError(f"HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OllamaRequestError(str(exc)) from exc
    elapsed_ms = (time.perf_counter() - started) * 1000
    if not isinstance(data, dict) or not isinstance(data.get("message"), dict):
        raise OllamaRequestError("Ollama returned an unexpected response shape.")
    content = data["message"].get("content")
    if not isinstance(content, str) or not content.strip():
        raise OllamaRequestError("Ollama returned an empty response.")
    return data, elapsed_ms


def metric_ms(data: dict, key: str) -> float | None:
    value = data.get(key)
    return value / 1_000_000 if isinstance(value, (int, float)) else None


def tokens_per_second(data: dict) -> float | None:
    token_count = data.get("eval_count")
    duration_ns = data.get("eval_duration")
    if not isinstance(token_count, int) or not isinstance(duration_ns, (int, float)) or duration_ns <= 0:
        return None
    return token_count / duration_ns * 1_000_000_000


def run_benchmark(models: list[str], base_url: str, warmup: bool) -> dict:
    cases = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    results = []
    model_runs = {model: [] for model in models}
    warmups = {}

    for model in models:
        if warmup:
            try:
                _data, warmup_ms = request_chat(
                    base_url,
                    model,
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": "Bonjour."},
                    ],
                )
                warmups[model] = {"status": "ok", "wall_ms": round(warmup_ms, 2)}
            except OllamaRequestError as exc:
                warmups[model] = {"status": "error", "error": str(exc)}
                print(f"[warmup error] {model}: {exc}", file=sys.stderr)

        for case in cases:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *case["messages"],
            ]
            run = {
                "model": model,
                "case_id": case["id"],
                "category": case["category"],
                "language": case["language"],
                "messages": case["messages"],
                "checks": case["checks"],
                "status": "ok",
                "response": None,
                "metrics": {},
                "error": None,
                "human_review": {
                    "helpfulness": None,
                    "language_match": None,
                    "grounding": None,
                    "context_use": None,
                    "hallucination": None,
                    "notes": "",
                },
            }
            try:
                data, wall_ms = request_chat(base_url, model, messages)
                run["response"] = data["message"]["content"].strip()
                run["metrics"] = {
                    "wall_ms": round(wall_ms, 2),
                    "ollama_total_ms": metric_ms(data, "total_duration"),
                    "load_ms": metric_ms(data, "load_duration"),
                    "prompt_tokens": data.get("prompt_eval_count"),
                    "prompt_eval_ms": metric_ms(data, "prompt_eval_duration"),
                    "generated_tokens": data.get("eval_count"),
                    "generation_ms": metric_ms(data, "eval_duration"),
                    "tokens_per_second": tokens_per_second(data),
                }
                print(f"[ok] {model} {case['id']} ({wall_ms:.0f} ms)")
            except OllamaRequestError as exc:
                run["status"] = "error"
                run["error"] = str(exc)
                print(f"[error] {model} {case['id']}: {exc}", file=sys.stderr)
            results.append(run)
            model_runs[model].append(run)

    summary = {}
    for model, runs in model_runs.items():
        successful = [run for run in runs if run["status"] == "ok"]
        wall_times = [run["metrics"]["wall_ms"] for run in successful]
        speeds = [
            run["metrics"]["tokens_per_second"]
            for run in successful
            if run["metrics"]["tokens_per_second"] is not None
        ]
        summary[model] = {
            "success_count": len(successful),
            "error_count": len(runs) - len(successful),
            "mean_wall_ms": round(sum(wall_times) / len(wall_times), 2) if wall_times else None,
            "mean_tokens_per_second": round(sum(speeds) / len(speeds), 2) if speeds else None,
            "human_scores": "complete human_review fields in each run before selecting a model",
        }

    return {
        "report_id": str(uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ollama_url": base_url,
        "dataset": str(DATASET_PATH.relative_to(BACKEND_DIR)),
        "system_prompt": SYSTEM_PROMPT,
        "environment_notes": {
            "machine": "",
            "os": "",
            "ollama_version": "",
            "hardware_acceleration": "",
            "notes": "",
        },
        "generation": {
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "max_tokens": MAX_TOKENS,
            "warmup_enabled": warmup,
            "timeout_seconds": TIMEOUT_SECONDS,
        },
        "models": models,
        "case_count": len(cases),
        "warmups": warmups,
        "summary": summary,
        "runs": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS, help="Ollama model tags to compare.")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama API base URL.")
    parser.add_argument("--output", type=Path, help="Output JSON path (default: timestamped local results file).")
    parser.add_argument("--no-warmup", action="store_true", help="Skip one unscored request per model.")
    args = parser.parse_args()

    report = run_benchmark(args.models, args.ollama_url, warmup=not args.no_warmup)
    output = args.output
    if output is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = BACKEND_DIR / "data" / "llm_eval" / "results" / f"benchmark-{timestamp}.json"
    elif not output.is_absolute():
        output = BACKEND_DIR / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved report: {output}")
    errors = sum(model_summary["error_count"] for model_summary in report["summary"].values())
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
