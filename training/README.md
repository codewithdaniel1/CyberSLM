# Adapter training

This directory defines the reviewed-data gate for optional local LoRA experiments. It does
not contain a production training corpus, and CyberSLM never exports conversations or eval
answers into one.

Each JSONL record must include `id`, `mode`, `split`, `source`, `license`,
`approved_for_training: true`, `contains_private_data: false`, and a `messages` array ending
in an assistant response. The manifest records the reviewer, review timestamp, allowed
licenses, exact corpus SHA-256, base model, version, and minimum approved sample count.

```bash
uv run cyberslm-train inspect --dataset data/training/corpus.jsonl
uv run cyberslm-train validate \
  --dataset data/training/corpus.jsonl \
  --manifest data/training/manifest.json
uv sync --extra mlx --extra train
uv run cyberslm-train run \
  --dataset data/training/corpus.jsonl \
  --manifest data/training/manifest.json \
  --output data/adapters/candidate-v1 \
  --confirm-reviewed
```

After training and controlled evaluation, set
`CYBERSLM_ADAPTER_PATH=data/adapters/candidate-v1/adapters.safetensors` to load the adapter.
Never promote an adapter merely because training loss decreased; compare it against the
RAG-only baseline on held-out quality, citation, safety, and refusal suites first.
