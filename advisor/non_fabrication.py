"""Evidence bag + non-fabrication checks (ADR-014)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable


_NUM_RE = re.compile(
    r"""
    (?<![A-Za-z0-9_./-])          # not mid-identifier
    [+-]?
    (?:
        \d+\.\d+(?:[eE][+-]?\d+)? # float / scientific
      | \d+(?:[eE][+-]?\d+)       # int scientific
      | \d+\.\d+                  # plain float
      | \d+                       # int
    )
    (?![A-Za-z0-9_])
    """,
    re.VERBOSE,
)

# Backend tokens we treat as claimable identifiers in the answer.
_BACKEND_RE = re.compile(
    r"\b(bentoml|ray-serve|triton|vllm|bedrock|gateway|reference-tiny-llm)\b"
)


@dataclass(frozen=True)
class EvidenceItem:
    tool: str
    kind: str  # "number" | "backend" | "bool" | "string"
    key: str
    value: Any
    value_str: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def format_number(value: float | int) -> str:
    """Canonical string form used in answers and evidence."""
    f = float(value)
    # Prefer compact but stable representation.
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    s = f"{f:.12g}"
    return s


def add_number(evidence: list[EvidenceItem], tool: str, key: str, value: float | int) -> str:
    s = format_number(value)
    evidence.append(EvidenceItem(tool=tool, kind="number", key=key, value=float(value), value_str=s))
    return s


def add_backend(evidence: list[EvidenceItem], tool: str, key: str, backend: str) -> str:
    b = str(backend).strip()
    evidence.append(EvidenceItem(tool=tool, kind="backend", key=key, value=b, value_str=b))
    return b


def add_string(evidence: list[EvidenceItem], tool: str, key: str, value: str) -> str:
    s = str(value)
    evidence.append(EvidenceItem(tool=tool, kind="string", key=key, value=s, value_str=s))
    return s


def add_bool(evidence: list[EvidenceItem], tool: str, key: str, value: bool) -> str:
    s = "true" if value else "false"
    evidence.append(EvidenceItem(tool=tool, kind="bool", key=key, value=bool(value), value_str=s))
    return s


def extract_numbers(text: str) -> list[str]:
    return [m.group(0) for m in _NUM_RE.finditer(text)]


def extract_backends(text: str) -> list[str]:
    return _BACKEND_RE.findall(text)


def _number_allowed(token: str, allowed: Iterable[str], allowed_floats: Iterable[float]) -> bool:
    if token in allowed:
        return True
    try:
        tv = float(token)
    except ValueError:
        return False
    for af in allowed_floats:
        if abs(tv - af) <= max(1e-12, abs(af) * 1e-9):
            return True
    return False


def assert_answer_grounded(answer: str, evidence: list[EvidenceItem]) -> None:
    """Fail if any number or known backend name in ``answer`` is not in evidence.

    This is the concrete ADR-014 / ADR-007 non-fabrication proof.
    """
    allowed_num_strs = {e.value_str for e in evidence if e.kind == "number"}
    allowed_floats = [float(e.value) for e in evidence if e.kind == "number"]
    allowed_backends = {e.value_str for e in evidence if e.kind == "backend"}
    allowed_bools = {e.value_str for e in evidence if e.kind == "bool"}

    for token in extract_numbers(answer):
        # Booleans rendered as true/false are not numbers; skip pure bool tokens.
        if token in allowed_bools:
            continue
        if not _number_allowed(token, allowed_num_strs, allowed_floats):
            raise AssertionError(
                f"non-fabrication FAIL: number {token!r} in answer is not in tool evidence "
                f"(allowed={sorted(allowed_num_strs)})"
            )

    for backend in extract_backends(answer):
        if backend not in allowed_backends:
            raise AssertionError(
                f"non-fabrication FAIL: backend {backend!r} in answer is not in tool evidence "
                f"(allowed={sorted(allowed_backends)})"
            )
