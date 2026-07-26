from vulcan_bedrock.pricing import cost_for_model, load_pricing_reference


def test_pricing_reference_is_static() -> None:
    ref = load_pricing_reference()
    assert ref["source"] == "static_reference"
    assert "disclaimer" in ref
    titan = ref["models"]["amazon.titan-text-express-v1"]
    assert "input_usd_per_1k_tokens" in titan
    assert "typical_latency_ms" in titan
    assert titan["typical_latency_ms"]["p50"] > 0


def test_cost_for_model() -> None:
    assert cost_for_model("missing-model") is None
    row = cost_for_model("amazon.titan-text-express-v1")
    assert row is not None
    assert row["source"] == "static_reference"
    assert row["output_usd_per_1k_tokens"] > 0
