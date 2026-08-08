"""Camelot wheel compatibility scoring."""

from __future__ import annotations


def _parse(code: str) -> tuple[int, str] | None:
    code = code.strip().upper()
    if len(code) < 2 or code[-1] not in "AB":
        return None
    try:
        num = int(code[:-1])
    except ValueError:
        return None
    if not 1 <= num <= 12:
        return None
    return num, code[-1]


def camelot_score(a: str, b: str) -> float:
    """1.0 same key; 0.9 neighbor or relative; 0.75 +2 (energy boost) or +7-ish
    (diagonal); 0.3 anything else. Unknown keys score neutral 0.6."""
    pa, pb = _parse(a), _parse(b)
    if pa is None or pb is None:
        return 0.6
    na, la = pa
    nb, lb = pb
    dist = min((na - nb) % 12, (nb - na) % 12)
    if la == lb:
        if dist == 0:
            return 1.0
        if dist == 1:
            return 0.9
        if dist == 2:
            return 0.75
        return 0.3
    # relative major/minor (same number) or diagonal neighbor
    if dist == 0:
        return 0.9
    if dist == 1:
        return 0.65
    return 0.3


def key_term(a: str, b: str, conf_a: float, conf_b: float) -> float:
    """Confidence-weighted key compatibility: with unreliable keys the term
    collapses to neutral 0.6 instead of trusting garbage."""
    conf = min(conf_a, conf_b)
    return conf * camelot_score(a, b) + (1.0 - conf) * 0.6
