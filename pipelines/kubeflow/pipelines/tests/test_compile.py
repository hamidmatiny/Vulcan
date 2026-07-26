from pathlib import Path

from vulcan_kfp.compile_pipeline import compile_to


def test_pipeline_compiles(tmp_path: Path) -> None:
    out = compile_to(tmp_path / "vulcan-reference-tiny-llm.yaml")
    text = out.read_text(encoding="utf-8")
    assert "vulcan-reference-tiny-llm" in text
    assert "train" in text.lower()
    assert "evaluate" in text.lower()
