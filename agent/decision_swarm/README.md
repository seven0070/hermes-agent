# Optional local decision heads (experimental)

Four small fastText classifiers sequentially answer `intent`, `complexity`, `tool_need`, and `tier` against the same input. Deterministic policy picks the fast model only for short, high-confidence, simple, no-tool lookup/chat. Ambiguity, missing packages/models, explicit `/model`, control commands, long or action-shaped messages fall back to the primary model. The primary Hermes agent and its existing tool/approval safeguards always run. This is not Jev's model or architecture, and fastText's raw scores are not calibrated confidence. No chat history is collected or trained on automatically.

The checked-in seed models and seed.tsv provide a tiny **demo baseline only** (22 synthetic examples). Real routing quality is not validated; leave this off for important work. The 4 model files total roughly 540 KB. Install an optional Windows-compatible fastText wheel in Hermes' Python environment (`uv pip install --python <venv-python> fasttext-wheel 'numpy<2'`). These versions worked in the scratch test, not on Windows. Confirm the dependency's wheel/license before redistributing binaries.

Add to `config.yaml` only when testing:

```yaml
decision_swarm:
  enabled: true
  fast_model: "openai/gpt-5.4-mini" # choose a known working model on the SAME configured provider
  fast_provider: "openrouter"    # must match the resolved primary runtime provider
  threshold: 0.85
```

Leave absent/false by default. For your own examples, create a UTF-8 TSV with the five columns in `seed.tsv` and label each example after reviewing it. Do not put secrets in training data. Prefer many varied and adversarial examples, hold back an independent evaluation file, and train explicitly:

```sh
python -m agent.decision_swarm --data examples.tsv --output <private-model-directory>
python -m agent.decision_swarm.eval --data heldout.tsv --models <private-model-directory>
```

Set `model_dir: <private-model-directory>` in config to use custom models. No training runs from live messages. The eval prints per-head accuracy and cold/warm CPU latency but does not establish calibrated probabilities or safe end-to-end routing. The lightweight fastText wheel is optional: if absent, the agent uses its primary model. Routing never changes provider credentials, so the fast model **must** exist with the same provider. Gateway foreground/background and CLI route before agent construction; other surfaces may not use this router. Benchmark on the target Windows PC before making it a default.

Source: https://fasttext.cc/docs/en/supervised-tutorial.html (fastText); https://github.com/facebookresearch/fastText/blob/main/LICENSE (MIT); https://docs.typesafe.ai/ (Jev inspiration, not a compatible or equivalent model).
