# LLM evaluation set (SA-31–33)

This dataset is for comparing Gemma and Qwen through Ollama. Ollama is the
local model runner; it is not itself a model. Each case contains the same
conversation messages and manual evaluation checks for every candidate model.
The set deliberately includes Tunisian Arabic, Arabizi, code-switching,
multi-turn context, and questions that must not receive invented official
IIT/ISB information.

## Run the evaluation

On the machine running Ollama, install the candidate models first:

    ollama pull gemma3:4b
    ollama pull qwen3:4b

From `backend/`, run:

    python scripts/benchmark_llm.py

The runner warms up each model, then sends every case to each model with the
same system prompt and generation options. It saves raw outputs and Ollama
timing/token metrics to a timestamped JSON file under
`data/llm_eval/results/`. Generated reports are local and are not intended for
Git.

To select other installed models or change the endpoint:

    python scripts/benchmark_llm.py --models gemma3:4b qwen3:8b
    python scripts/benchmark_llm.py --ollama-url http://127.0.0.1:11434

The results include empty human-review fields. Complete these manually using
the rubric below; do not use an LLM to grade another LLM's answers for the
official comparison.

## Human scoring rubric

Score each applicable dimension from 1 to 5:

| Score | Meaning |
|---|---|
| 1 | Incorrect, unusable, or unsafe |
| 2 | Major omission, misunderstanding, or unsupported claim |
| 3 | Partly useful, but has a notable issue |
| 4 | Good answer with only a minor issue |
| 5 | Correct, helpful, appropriately cautious, and natural |

For each response, fill `human_review` in the output JSON:

- `helpfulness`: answers the student's intent and asks a useful question when
  context is missing.
- `language_match`: understands the expected language and responds naturally;
  for Tunisian/Arabizi, mark whether the intent was understood even if the
  assistant sensibly switches to French.
- `grounding`: avoids unsupported facts and clearly handles uncertainty.
- `context_use`: uses the conversation history correctly; mark N/A for
  single-turn cases.
- `hallucination`: true if the answer asserts an unsupported official fact,
  exact fee/date/requirement, or guaranteed outcome.
- `notes`: short explanation for scores and any hallucination.

Never award a high grounding score to a confident but unverified official
claim. A fabricated exact admission requirement, fee, or date is a critical
failure, regardless of the model's other scores.

For a summary, report each dimension's mean score, critical hallucination
count, failed/error count, mean wall-clock latency, and generated tokens per
second. A practical selection gate is zero critical official-fact
hallucinations in the grounding cases, followed by the best language,
helpfulness, and context scores at an acceptable latency. Record the machine,
Ollama version, model tags, and any hardware acceleration in the report notes;
latency is hardware-dependent.

## Scope and limitations

The set is a first evaluation baseline, not a representative Tunisian
language corpus or an admissions knowledge base. It intentionally does not
assert the actual IIT/ISB admission facts. Add reviewed cases from the team's
own experience, and use official source documents before scoring factual
admission QA with an answer key. Prompts are not sufficient evidence for a
production selection without human review.
