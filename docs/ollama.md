# CyberSLM-Crypto Ollama workflow

Ollama is one CyberSLM-Crypto deployment target, not the canonical or exclusive format. The canonical
fine-tuned artifact will be a local PEFT Safetensors adapter plus a merged Safetensors checkpoint;
GGUF and Ollama models are derived from the accepted merged checkpoint. Hugging Face Hub work is
deferred. The target name includes the base family, size, and specialty:
`gemma3-4b-cyberslm-crypto`.

The checked-in Modelfile currently creates a development model from the untouched Gemma 3 4B
base. It is a baseline, not yet a fine-tuned model.

Republish the local alias whenever the tracked Modelfile changes or an accepted derived model is
available:

```bash
uv run cyberslm-ollama publish-local
```

This updates the local `gemma3-4b-cyberslm-crypto:dev` alias and reuses existing Ollama weight
layers. Training docs, curriculum drafts, and evaluation changes do not alter weights, so they do
not change the scorecard until an actual fine-tune is promoted.

## Import a derived GGUF candidate

After a merged Safetensors candidate has passed artifact validation, convert it with a compatible
llama.cpp converter, quantize it, hash the final GGUF, and import it without editing a local
Modelfile by hand:

```bash
uv run cyberslm-ollama import-gguf \
  --gguf data/adapters/gemma3-4b-cyberslm-crypto-ctf-sft-v0/gguf/gemma3-4b-cyberslm-crypto-ctf-sft-v0-Q4_K_M.gguf \
  --model gemma3-4b-cyberslm-crypto:0.1.0-rc1
```

`import-gguf` uses the tracked crypto system prompt and parameters from
`ollama/Modelfile.gemma3-4b`, replacing only its `FROM` line with the immutable local GGUF path.
The `0.1.0-rc1` tag is experimental; it is not a release designation until the held-out
comparison gate passes.

## Build and run the baseline

Install and start Ollama, then run from the repository root:

```bash
ollama pull gemma3:4b
ollama create gemma3-4b-cyberslm-crypto:dev -f ollama/Modelfile.gemma3-4b
ollama run gemma3-4b-cyberslm-crypto:dev
```

No GitHub release or Ollama upload is required for local use. Ollama stores the pulled base and
created model in its own managed model store rather than this Git repository.

## Evaluate through CyberSLM-Crypto

The `ollama` backend calls the local API at `http://127.0.0.1:11434` by default. It supports the
same text, image, generation-metadata, evaluation, and optional CyberSLM RAG contracts as the
existing runtimes.

```bash
uv run cyberslm-eval run \
  --backend ollama \
  --model gemma3-4b-cyberslm-crypto:dev \
  --dataset evals/datasets/crypto-v1.jsonl \
  --rag-policy off \
  --temperature 0

uv run cyberslm-eval run \
  --backend ollama \
  --model gemma3-4b-cyberslm-crypto:dev \
  --dataset evals/datasets/crypto-v1.jsonl \
  --rag-policy off \
  --temperature 0

uv run cyberslm-benchmark \
  --backend ollama \
  --model gemma3-4b-cyberslm-crypto:dev \
  --label ollama-base
```

Set `CYBERSLM_OLLAMA_BASE_URL` only when Ollama listens somewhere else. Increasing
`CYBERSLM_OLLAMA_TIMEOUT` can help with slow cold starts. Evaluations explicitly default to a
4,096-token Ollama context through `CYBERSLM_OLLAMA_CONTEXT_SIZE`; keep it identical across model
comparisons so models with very large native context defaults do not consume disproportionate
memory or spill generation onto the CPU.

The CyberSLM evaluation backend also explicitly overrides any system prompt embedded in an Ollama
Modelfile. This prevents a named development model from receiving both its baked prompt and the
repository's backend-independent evaluation prompt. Direct `ollama run` usage is unaffected and
continues to use the Modelfile system prompt.

## Fine-tuned artifact

The intended first training release is `gemma3-4b-cyberslm-crypto:0.1`. Its high-level flow is:

1. validate a separately licensed, provenance-tracked, human-approved SFT corpus;
2. run a controlled Unsloth LoRA/QLoRA experiment;
3. merge the accepted adapter into the exact training base;
4. export a compatible GGUF artifact and create the Ollama model from it; and
5. adopt it only after it beats the untouched Ollama baseline without weakening safety.

The first experimental candidate (`gemma3-4b-cyberslm-crypto:0.1.0-rc1`) has an imported Q4_K_M
GGUF locally. It remains an evaluation candidate, not a release.

Only approved crypto standards material and reviewed instruction data may become RAG or training
inputs. Historical ATT&CK, CWE, and CAPEC content is not part of this model's scope.

## RAG and user interface

Ollama runs the model but does not bundle CyberSLM's searchable knowledge database into the model
artifact. During the transition, the existing retrieval and evaluation path can send grounded
prompts to the Ollama backend. A later milestone will connect the model to Open WebUI or Onyx and
compare that knowledge workflow with CyberSLM's current provenance-aware retriever.

Running `ollama run gemma3-4b-cyberslm-crypto:<version>` by itself uses only the model weights and system
prompt; it does not query an optional crypto standards bundle. To get RAG, attach the Ollama model to
a RAG client such as Open WebUI and load a knowledge collection, or put CyberSLM's retriever in
front of the Ollama API. The latter preserves CyberSLM's pinned sources and citation controls.

CyberSLM no longer maintains a tracked chat UI. Use Ollama directly or connect the resulting model
to any compatible interface; keep the knowledge index external when RAG is required.

## GitHub release package

The public Ollama artifact will be downloadable from a versioned GitHub Release rather than stored
in normal Git history. Because GitHub requires each release asset to be under 2 GiB, the GGUF will
be packaged as deterministic parts when necessary. The release will include part hashes, the
expected reconstructed GGUF hash, cross-platform reconstruction commands, and this Modelfile.
Users will not need the CyberSLM Python package merely to run the reconstructed GGUF in Ollama.

## Historical AppSec baseline result

On 2026-09-09, the local predecessor `gemma3-4b-cyberslm:dev` GGUF Q4_K_M model completed all six smoke cases
at the normal 1,024-token limit without truncation. It passed 5/6 automatic checks without RAG;
the remaining answer was substantively correct but missed an exact wording alternative. Auto-RAG
passed 4/6 and revealed an unsafe SSRF validation suggestion plus weak citation attribution.
Those results are retained as historical evidence and are not a CyberSLM-Crypto release gate.

## Primary references

- [Ollama generate API](https://docs.ollama.com/api/generate)
- [Ollama model import, quantization, and sharing](https://docs.ollama.com/import)
- [Unsloth Gemma 3 fine-tuning guide](https://docs.unsloth.ai/basics/tutorial-how-to-run-and-fine-tune-gemma-3)
