# Selected Public Model

The selected non-vLLM inference model is `amazon/chronos-t5-small`.

Source: https://huggingface.co/amazon/chronos-t5-small

Category: pretrained time-series forecasting transformer.

Role in this project:

- Serve probabilistic forecasts from historical numeric time-series values.
- Return normalized forecast summaries, risk bands, confidence, and proxy driver contributions.
- Stay separate from the vLLM service. Chronos handles numeric forecasting; vLLM handles explanation and recommendation text.

Operational notes:

- The service uses CPU by default for OCI E6 AX compatibility.
- The public Chronos model is lazy-loaded on first prediction when `ML_LOAD_PUBLIC_MODEL=true`.
- If Chronos dependencies, model download, or inference fail, the service returns a deterministic trend fallback and includes a warning.
- This project does not train or fine-tune Chronos.

Production caveats to check:

- Apache-2.0 license and any dependency licenses.
- Latency and memory on the exact E6 AX shape.
- Forecast quality on the target domain and forecast horizon.
- Whether a newer Chronos/Chronos-Bolt checkpoint is a better operational fit.

