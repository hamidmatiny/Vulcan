from vulcan_model_contract.validate import validate_instance


def test_health_ok(api_client) -> None:
    resp = api_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "bedrock"
    assert body["status"] == "ok"
    validate_instance(body, "health")


def test_resources_and_pricing(api_client) -> None:
    res = api_client.get("/v1/resources")
    assert res.status_code == 200
    assert res.json()["backend"] == "bedrock"
    assert res.json()["cpu_dev_mode"] is True

    pricing = api_client.get("/v1/pricing-reference")
    assert pricing.status_code == 200
    data = pricing.json()
    assert data["source"] == "static_reference"
    assert "amazon.titan-text-express-v1" in data["models"]
    assert "how_to_replace_with_real_measurements" in data


def test_infer_llm_contract_shape(api_client) -> None:
    payload = {
        "request_id": "bedrock-1",
        "modality": "llm",
        "model_id": "amazon.titan-text-express-v1",
        "input": {
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 16,
            "temperature": 0.0,
        },
    }
    resp = api_client.post("/v1/infer", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    validate_instance(body, "infer-response")
    assert body["modality"] == "llm"
    assert body["output"]["text"] == "hello from titan"
    assert body["latency_ms"] >= 0


def test_vision_unsupported(api_client) -> None:
    payload = {
        "request_id": "bedrock-v",
        "modality": "vision",
        "model_id": "reference-tiny-vision",
        "input": {
            "images": [
                {
                    "media_type": "image/png",
                    "data_base64": "aGVsbG8=",
                }
            ]
        },
    }
    resp = api_client.post("/v1/infer", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error"] == "unsupported_modality"


def test_metrics_exposes_prometheus(api_client) -> None:
    api_client.post(
        "/v1/infer",
        json={
            "request_id": "m1",
            "modality": "llm",
            "model_id": "amazon.titan-text-express-v1",
            "input": {"messages": [{"role": "user", "content": "x"}]},
        },
    )
    metrics = api_client.get("/metrics")
    assert metrics.status_code == 200
    assert "vulcan_infer_requests_total" in metrics.text
