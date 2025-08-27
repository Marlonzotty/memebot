import pytest

from app.utils.solana_normalizer import (
    compute_flags,
    compute_local_score,
    classify_token,
    attach_local_scoring,
)

def test_compute_flags_basico():
    snap = {
        "liquidityUSD": 10_000,
        "mcapUSD": 250_000,
        "fdvUSD": 300_000,
        "holders": 800,
        "ageMinutes": 180,
        "volumeUSD_5m": 4_000,
        "txnsBuy_5m": 40,
        "txnsSell_5m": 20,
        "buySellPressure_5m": (40 - 20) / (40 + 20),  # 0.333...
        "mintAuthorityDisabled": True,
        "freezeAuthorityDisabled": True,
        "links": [{"type":"website","url":"https://x"}],
    }
    flags = compute_flags(snap)
    assert "low_liq" not in flags
    assert "no_socials" not in flags
    assert "too_new" not in flags

def test_compute_flags_negativos():
    snap = {
        "liquidityUSD": 1000,
        "mcapUSD": 200_000,
        "holders": 50,
        "ageMinutes": 10,
        "volumeUSD_5m": 200,
        "buySellPressure_5m": -0.5,
        "mintAuthorityDisabled": False,
        "freezeAuthorityDisabled": False,
        "links": [],
        "fdvUSD": 1_500_000,
    }
    flags = compute_flags(snap)
    for f in [
        "low_liq","low_holders","too_new","low_volume_5m",
        "weak_pressure","no_socials","mint_enabled","freeze_enabled",
        "high_fdv_vs_mcap"
    ]:
        assert f in flags

def test_compute_local_score_intervalo():
    snap = {
        "liquidityUSD": 15_000,
        "mcapUSD": 400_000,
        "holders": 1200,
        "ageMinutes": 150,
        "volumeUSD_5m": 5_000,
        "buySellPressure_5m": 0.2,
        "mintAuthorityDisabled": True,
        "freezeAuthorityDisabled": True,
        "links": [{"type":"website","url":"https://x"}],
    }
    score, breakdown = compute_local_score(snap)
    assert 0 <= score <= 100
    assert all(0.0 <= v <= 1.0 for v in breakdown.values())

def test_classify_token_regras():
    assert classify_token(80.0, []) == "high_potential"
    assert classify_token(60.0, []) == "watchlist"
    assert classify_token(95.0, ["mint_enabled"]) == "discard"

def test_attach_local_scoring_adiciona_campos():
    snap = {
        "liquidityUSD": 10_000,
        "mcapUSD": 300_000,
        "holders": 600,
        "ageMinutes": 120,
        "volumeUSD_5m": 3_000,
        "buySellPressure_5m": 0.1,
        "mintAuthorityDisabled": True,
        "freezeAuthorityDisabled": True,
        "links": [{"type":"website","url":"https://x"}],
    }
    out = attach_local_scoring(snap)
    assert "score_local" in out
    assert "score_breakdown" in out and isinstance(out["score_breakdown"], dict)
    assert "flags" in out and isinstance(out["flags"], list)
    assert out.get("classification") in {"high_potential","watchlist","discard"}
