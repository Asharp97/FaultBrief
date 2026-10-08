# Model experiments

Reserve this directory for the narrow diagnostic-path classifier experiment after the investigation baseline and evaluation cases exist.

- Start with a small pretrained model and measure memory use on a short local trial.
- Keep train/validation/test splits grouped by scenario template to avoid near-duplicate leakage.
- Record dataset version, base-model revision, settings, seed, runtime, metrics, and errors.
- Compare a tuned model against simple rules and an untuned baseline before serving it.
- Keep large checkpoints in ignored `artifacts/`; keep private data in ignored `data/private/`.
- Publish only permitted data/artifacts with a model card and honest limitations.

No GPU frameworks or model weights are installed by repository setup. Create a separately locked training environment when the experiment is defined, so heavy GPU dependencies do not inflate the API environment.
