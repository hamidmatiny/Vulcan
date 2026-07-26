from vulcan_bedrock.client import (
    build_invoke_body,
    messages_to_prompt,
    parse_invoke_response,
)


def test_messages_to_prompt() -> None:
    text = messages_to_prompt(
        [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
        ]
    )
    assert "system: be brief" in text
    assert "user: hi" in text


def test_build_invoke_body_titan_and_claude() -> None:
    msgs = [{"role": "user", "content": "hello"}]
    titan_body, _ = build_invoke_body(
        model_id="amazon.titan-text-express-v1",
        messages=msgs,
        max_tokens=16,
        temperature=0.2,
    )
    assert b"inputText" in titan_body
    claude_body, _ = build_invoke_body(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        messages=msgs,
        max_tokens=16,
        temperature=0.0,
    )
    assert b"max_tokens_to_sample" in claude_body


def test_parse_titan_response() -> None:
    raw = b'{"inputTextTokenCount":2,"results":[{"outputText":"ok","tokenCount":1}]}'
    out = parse_invoke_response("amazon.titan-text-express-v1", raw)
    assert out["text"] == "ok"
    assert out["usage"]["total_tokens"] == 3


def test_infer_llm_uses_mocked_runtime(bedrock_client) -> None:
    out = bedrock_client.infer_llm(
        model_id="amazon.titan-text-express-v1",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=8,
    )
    assert out["text"] == "hello from titan"
    assert out["finish_reason"] == "stop"
