# app/utils/solana_normalizer.py
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

def _to_iso(ts: Optional[int]) -> Optional[str]:
    if ts is None:
        return None
    try:
        # Solscan costuma enviar epoch em segundos
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return None

def _age_minutes(listed_at_iso: Optional[str]) -> Optional[int]:
    if not listed_at_iso:
        return None
    try:
        listed = datetime.fromisoformat(listed_at_iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - listed
        return int(delta.total_seconds() // 60)
    except Exception:
        return None

def _links_from_meta(meta: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    site = meta.get("website") or meta.get("site")
    tg = meta.get("telegram")
    tw = meta.get("twitter") or meta.get("x")
    dc = meta.get("discord")
    if site:
        out.append({"type": "website", "url": site})
    if tg:
        out.append({"type": "telegram", "url": tg})
    if tw:
        out.append({"type": "twitter", "url": tw})
    if dc:
        out.append({"type": "discord", "url": dc})
    return out


def normalize_solscan_meta_to_snapshot(meta: Dict[str, Any], mint: str) -> Dict[str, Any]:
    """
    Converte o JSON 'meta' da Solscan em um snapshot mínimo
    compatível com seu pipeline (usado pelo analyze_tokens).
    """
    listed_iso = _to_iso(meta.get("first_trade_time") or meta.get("created_time"))
    age_min = _age_minutes(listed_iso)

    snapshot: Dict[str, Any] = {
        "tokenAddress": mint,
        "url": None,
        "header": meta.get("symbol") or meta.get("name") or "",
        "description": meta.get("description") or "",
        "chainId": "solana",  # seu normalize_chain_id converte para 101
        "links": _links_from_meta(meta),

        "listedAt": listed_iso,
        "ageMinutes": age_min,
        "holders": meta.get("holder"),

        "mintAuthorityDisabled": (meta.get("mint_authority") in (None, "", "disabled")),
        "freezeAuthorityDisabled": (meta.get("freeze_authority") in (None, "", "disabled")),

        # Enriquecimentos (preencheremos depois)
        "liquidityUSD": None,
        "mcapUSD": None,
        "fdvUSD": None,

        "volumeUSD_5m": None,
        "volumeUSD_1h": None,
        "volumeUSD_24h": None,

        "txnsBuy_5m": None, "txnsSell_5m": None,
        "txnsBuy_15m": None, "txnsSell_15m": None,
        "txnsBuy_1h": None, "txnsSell_1h": None,

        "buyers_5m": None, "sellers_5m": None,
        "buyers_1h": None, "sellers_1h": None,

        "lpLockedPct": None,
        "lpLockProvider": None,

        "creatorWalletActive": None,
        "devWalletBuys": None,
        "devWalletSells": None,

        "proxy": None,
        "upgradeable": None,
        "blacklistFn": None,

        "maxTx": None,
        "maxWallet": None,
        "taxBuy": None,
        "taxSell": None,

        "honeypotRisk": None,
        "rugcheckScore": None,

        "dexscreenerUrl": None,
        "dextoolsUrl": None,
        "birdeyeUrl": None,
        "solscanUrl": f"https://solscan.io/token/{mint}",
        "pairUrl": None,
        "chain": "sol",
    }
    return snapshot
    # <- MUITO IMPORTANTE


# --------------------------------------
# MERGE DO BIRDEYE NO SNAPSHOT (ENRIQUECIMENTO)
# --------------------------------------
def merge_birdeye_into_snapshot(
    snapshot: Dict[str, Any],
    overview: Optional[Dict[str, Any]] = None,
    volume: Optional[Dict[str, Any]] = None,
    trades5m: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Mescla dados do Birdeye (ou mocks) no snapshot já existente.
    Preenche liquidez, mcap/fdv, volumes e pressão de compra/venda.
    """
    # Overview (liq / mcap / fdv / vol 24h)
    if overview and isinstance(overview, dict):
        d = overview.get("data") or {}
        snapshot["liquidityUSD"] = d.get("liquidity", snapshot.get("liquidityUSD"))
        snapshot["mcapUSD"] = d.get("market_cap", snapshot.get("mcapUSD"))
        snapshot["fdvUSD"] = d.get("fdv", snapshot.get("fdvUSD"))
        snapshot["volumeUSD_24h"] = d.get("volume_24h_quote", snapshot.get("volumeUSD_24h"))

    # Volume por pontos (ex.: 1h com último ponto "5m")
    if volume and isinstance(volume, dict):
        d = volume.get("data") or {}
        pts = d.get("points") or []
        if pts:
            last = pts[-1]
            snapshot["volumeUSD_5m"] = last.get("volume_quote", snapshot.get("volumeUSD_5m"))
            snapshot["txnsBuy_5m"] = last.get("buy", snapshot.get("txnsBuy_5m"))
            snapshot["txnsSell_5m"] = last.get("sell", snapshot.get("txnsSell_5m"))
        if len(pts) >= 1:
            first = pts[0]
            snapshot["volumeUSD_1h"] = first.get("volume_quote", snapshot.get("volumeUSD_1h"))

    # Janela curta (5m) com agregados de buys/sells e compradores/vendedores
    if trades5m and isinstance(trades5m, dict):
        d = trades5m.get("data") or {}
        snapshot["buyers_5m"] = d.get("buyers", snapshot.get("buyers_5m"))
        snapshot["sellers_5m"] = d.get("sellers", snapshot.get("sellers_5m"))
        snapshot["txnsBuy_5m"] = snapshot.get("txnsBuy_5m") or d.get("buys")
        snapshot["txnsSell_5m"] = snapshot.get("txnsSell_5m") or d.get("sells")

    # Derivados úteis
    liq = snapshot.get("liquidityUSD") or 0
    mcap = snapshot.get("mcapUSD") or snapshot.get("fdvUSD") or 0
    try:
        snapshot["capLiqRatio"] = (float(mcap) / float(liq)) if (liq and mcap) else None
    except Exception:
        snapshot["capLiqRatio"] = None

    b = snapshot.get("txnsBuy_5m")
    s = snapshot.get("txnsSell_5m")
    try:
        b = float(b) if b is not None else 0.0
        s = float(s) if s is not None else 0.0
        snapshot["buySellPressure_5m"] = (b / s) if s > 0 else (b if b > 0 else None)
    except Exception:
        snapshot["buySellPressure_5m"] = None
        

    return snapshot

def merge_birdeye_into_snapshot(
    snapshot: Dict[str, Any],
    overview: Optional[Dict[str, Any]] = None,
    volume: Optional[Dict[str, Any]] = None,
    trades5m: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Mescla dados do Birdeye (ou mocks) no snapshot já existente.
    Preenche liquidez, mcap/fdv, volumes e pressão de compra/venda.
    """
    # Overview (liq / mcap / fdv / vol 24h)
    if overview and isinstance(overview, dict):
        d = overview.get("data") or {}
        snapshot["liquidityUSD"] = d.get("liquidity", snapshot.get("liquidityUSD"))
        snapshot["mcapUSD"] = d.get("market_cap", snapshot.get("mcapUSD"))
        snapshot["fdvUSD"] = d.get("fdv", snapshot.get("fdvUSD"))
        snapshot["volumeUSD_24h"] = d.get("volume_24h_quote", snapshot.get("volumeUSD_24h"))

    # Volume por pontos (ex.: série de 5m)
    pts = []
    if volume and isinstance(volume, dict):
        d = volume.get("data") or {}
        pts = d.get("points") or []

        if pts:
            last = pts[-1]
            snapshot["volumeUSD_5m"] = last.get("volume_quote", snapshot.get("volumeUSD_5m"))
            snapshot["txnsBuy_5m"] = last.get("buy", snapshot.get("txnsBuy_5m"))
            snapshot["txnsSell_5m"] = last.get("sell", snapshot.get("txnsSell_5m"))

        # volumeUSD_1h = soma dos últimos 12 pontos de 5m (ou de todos se < 12)
        if pts:
            take = pts[-12:] if len(pts) >= 12 else pts
            try:
                snapshot["volumeUSD_1h"] = float(sum(float(p.get("volume_quote", 0) or 0) for p in take))
            except Exception:
                snapshot["volumeUSD_1h"] = snapshot.get("volumeUSD_1h")

    # Janela curta (5m) com agregados (se vierem por outro endpoint)
    if trades5m and isinstance(trades5m, dict):
        d = trades5m.get("data") or {}
        snapshot["buyers_5m"] = d.get("buyers", snapshot.get("buyers_5m"))
        snapshot["sellers_5m"] = d.get("sellers", snapshot.get("sellers_5m"))
        snapshot["txnsBuy_5m"] = snapshot.get("txnsBuy_5m") or d.get("buys")
        snapshot["txnsSell_5m"] = snapshot.get("txnsSell_5m") or d.get("sells")

    # Derivados úteis
    liq = snapshot.get("liquidityUSD") or 0
    mcap = snapshot.get("mcapUSD") or snapshot.get("fdvUSD") or 0
    try:
        snapshot["capLiqRatio"] = (float(mcap) / float(liq)) if (liq and mcap) else None
    except Exception:
        snapshot["capLiqRatio"] = None

    # Pressão -1..+1: (buys - sells) / (buys + sells)
    b = snapshot.get("txnsBuy_5m")
    s = snapshot.get("txnsSell_5m")
    try:
        b = float(b) if b is not None else 0.0
        s = float(s) if s is not None else 0.0
        denom = b + s
        if denom > 0:
            snapshot["buySellPressure_5m"] = (b - s) / denom
        elif b > 0 and s == 0:
            snapshot["buySellPressure_5m"] = 1.0
        elif s > 0 and b == 0:
            snapshot["buySellPressure_5m"] = -1.0
        else:
            snapshot["buySellPressure_5m"] = None
    except Exception:
        snapshot["buySellPressure_5m"] = None

    # >>> NOVO: score local + flags + classificação
    try:
        snapshot = attach_local_scoring(snapshot)
    except Exception:
        # Em caso de erro, seguimos devolvendo o enriched sem score
        pass

    return snapshot

# --------------------------------------
# SCORING & FLAGS (LOCAL, PRÉ-GPT)
# --------------------------------------
def _clamp(x: float, a: float, b: float) -> float:
    return max(a, min(b, x))

def _minmax(x: Optional[float], lo: float, hi: float) -> float:
    if x is None:
        return 0.0
    if hi <= lo:
        return 0.0
    return _clamp((float(x) - lo) / (hi - lo), 0.0, 1.0)

def _zcurve(x: Optional[float], mid: float, width: float) -> float:
    if x is None:
        return 0.0
    # sigmoid ~ centrada em 'mid'
    import math
    return 1.0 / (1.0 + math.exp(-((float(x) - mid) / max(1e-9, width))))

def _has_socials(links: Optional[List[Dict[str, str]]]) -> bool:
    if not links:
        return False
    return any((l.get("type") in {"website","twitter","telegram","discord"}) and l.get("url") for l in links)

def compute_flags(snapshot: Dict[str, Any]) -> List[str]:
    flags: List[str] = []

    liq = snapshot.get("liquidityUSD")
    mcap = snapshot.get("mcapUSD")
    fdv  = snapshot.get("fdvUSD")
    holders = snapshot.get("holders")
    age_min = snapshot.get("ageMinutes")
    cap_liq = (float(mcap) / float(liq)) if (liq not in (None, 0) and mcap) else None

    pressure_5m = snapshot.get("buySellPressure_5m")  # -1..+1
    vol_5m = snapshot.get("volumeUSD_5m")
    links = snapshot.get("links") or []
    has_socials = _has_socials(links)

    mint_disabled   = bool(snapshot.get("mintAuthorityDisabled"))
    freeze_disabled = bool(snapshot.get("freezeAuthorityDisabled"))

    if liq is None or liq < 3000:
        flags.append("low_liq")
    if holders is None or holders < 200:
        flags.append("low_holders")
    if cap_liq is not None and cap_liq > 80:
        flags.append("high_cap_liq")
    if not has_socials:
        flags.append("no_socials")
    if age_min is not None and age_min < 30:
        flags.append("too_new")
    if pressure_5m is not None and pressure_5m < -0.25:
        flags.append("weak_pressure")
    if vol_5m is None or vol_5m < 1500:
        flags.append("low_volume_5m")
    if not mint_disabled:
        flags.append("mint_enabled")
    if not freeze_disabled:
        flags.append("freeze_enabled")
    if fdv and mcap and fdv > 5 * mcap:
        flags.append("high_fdv_vs_mcap")

    return flags

def compute_local_score(snapshot: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    liq = snapshot.get("liquidityUSD") or 0
    mcap = snapshot.get("mcapUSD") or 0
    holders = snapshot.get("holders") or 0
    age_min = snapshot.get("ageMinutes") or 0
    vol_5m = snapshot.get("volumeUSD_5m") or 0
    pressure_5m = snapshot.get("buySellPressure_5m")
    cap_liq = (float(mcap) / float(liq)) if (liq not in (None, 0)) else None

    mint_disabled   = bool(snapshot.get("mintAuthorityDisabled"))
    freeze_disabled = bool(snapshot.get("freezeAuthorityDisabled"))
    social_ok = _has_socials(snapshot.get("links"))

    # Normalizações (0..1)
    n_liq       = _minmax(liq, 3_000, 50_000)
    n_vol_5m    = _minmax(vol_5m, 1_500, 50_000)
    n_pressure  = _clamp(((pressure_5m or 0.0) + 1.0) / 2.0, 0.0, 1.0)
    n_holders   = _minmax(holders, 200, 5_000)
    n_age       = _zcurve(age_min, mid=120, width=60)  # melhor após ~2h
    n_capliq    = 1.0 - _minmax((cap_liq if cap_liq is not None else 9999), 60, 100)
    n_authority = 1.0 if (mint_disabled and freeze_disabled) else 0.0
    n_socials   = 1.0 if social_ok else 0.0

    W = {
        "liq": 0.18,
        "vol_5m": 0.16,
        "pressure_5m": 0.16,
        "cap_liq": 0.14,
        "holders": 0.12,
        "age": 0.08,
        "authority": 0.08,
        "socials": 0.08,
    }
    comp = {
        "liq": n_liq,
        "vol_5m": n_vol_5m,
        "pressure_5m": n_pressure,
        "cap_liq": n_capliq,
        "holders": n_holders,
        "age": n_age,
        "authority": n_authority,
        "socials": n_socials,
    }
    score01 = sum(W[k] * comp[k] for k in W.keys())
    score = round(100.0 * _clamp(score01, 0.0, 1.0), 2)
    return score, comp

def classify_token(score: float, flags: List[str]) -> str:
    critical = {"mint_enabled", "freeze_enabled", "too_new"}
    if any(f in critical for f in flags):
        return "discard"
    if score >= 72 and not any(f in flags for f in ("low_liq","weak_pressure","low_volume_5m","high_cap_liq")):
        return "high_potential"
    if score >= 55:
        return "watchlist"
    return "discard"

def attach_local_scoring(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    flags = compute_flags(snapshot)
    score, breakdown = compute_local_score(snapshot)
    label = classify_token(score, flags)
    snapshot["score_local"] = score
    snapshot["score_breakdown"] = breakdown
    snapshot["flags"] = flags
    snapshot["classification"] = label
    return snapshot