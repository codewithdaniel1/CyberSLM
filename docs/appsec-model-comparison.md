# CyberSLM-AppSec model comparison

Status: preliminary baseline, 2026-09-09

CyberSLM-AppSec compares every trained candidate with both its untouched base and a strong public
cybersecurity model. The first comparison set is:

- `gemma3:4b` — untouched size-matched base;
- `gemma3-4b-cyberslm-appsec:dev` — current prompt-only development model; and
- `hf.co/gabriellarson/Foundation-Sec-8B-Instruct-GGUF:Q4_K_M` — larger cyber baseline.

The held-out `evals/datasets/appsec-v1.jsonl` suite contains 12 secure-code cases covering
vulnerability identification, evidence restraint, remediation, false-positive avoidance, and safe
verification. It deliberately does not require CWE numbers. These initial labels are AI-authored
drafts and must be human-approved before the suite becomes a release gate.

## Preliminary automatic result

All runs used Ollama, RAG off, temperature 0, a 700-token output limit, and a 4,096-token context.

| Model | Parameters | Pass rate | Mean concept score | Mean latency |
| --- | ---: | ---: | ---: | ---: |
| Gemma 3 base | 4B | 33.3% | 0.5754 | 8.96 s |
| CyberSLM-AppSec prompt-only development model | 4B | 33.3% | 0.5754 | 8.74 s |
| Foundation-Sec-8B-Instruct Q4_K_M | 8B | 41.7% | 0.5869 | 34.30 s |

All three passed the automatic allowed-behavior check without a false refusal. Foundation-Sec is
the current automatic quality leader by a narrow mean-score margin, but it was about 3.8 times
slower than untouched Gemma on this Mac and one response hit the 700-token limit. Its first attempt
also caused the local Ollama service to disconnect when the model used a 16,384-token context; the
successful comparison used the common 4,096-token setting.

An early prompt-only run was invalidated after inspection showed that the Ollama Modelfile system
prompt was stacked with the evaluator's complete CyberSLM prompt. The adapter now sends one
explicit system message and one conversation prompt to every Ollama model, overriding embedded
system text. The clean Gemma and CyberSLM-AppSec rows are identical within timing noise, confirming
that the alias has not degraded the shared weights. The development model is not a fine-tuned-model
result.

## Base-selection rule

1. Human-approve or correct every AppSec v1 label, then review all saved responses blind to model
   identity.
2. Train one controlled Gemma 3 4B CyberSLM-AppSec candidate and compare it with both baselines
   under identical settings.
3. Give the Gemma candidate one correction cycle for demonstrated data or training defects.
4. If the corrected Gemma candidate does not beat Foundation-Sec on the human-reviewed AppSec
   quality gate without weakening safety, make Foundation-Sec-8B-Instruct the next training-base
   candidate.
5. Before switching, validate local Unsloth loading, training memory, the complete Llama 3.1 and
   Cisco notice obligations, and GGUF conversion from the original Safetensors checkpoint.

The installed GGUF is evaluation-only and cannot be the canonical training input. A switch would
use the original `fdtn-ai/Foundation-Sec-8B-Instruct` Safetensors checkpoint and produce artifacts
named `foundation-sec-8b-cyberslm-appsec`.

## Reproduce

Run each model with the same command shape:

```bash
uv run cyberslm-eval run \
  --backend ollama \
  --model MODEL_NAME \
  --dataset evals/datasets/appsec-v1.jsonl \
  --rag-policy off \
  --temperature 0 \
  --max-tokens 700 \
  --ollama-context-size 4096
```

Local reports and review worksheets remain ignored because they contain complete model responses
and machine-specific timing data.
