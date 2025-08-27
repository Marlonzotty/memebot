# app/utils/filters.py
from typing import Dict, Optional, List
import re

# ---------- thresholds (afrouxe conforme necessário) ----------
MAX_TOKEN_AGE_SECONDS = 30 * 24 * 60 * 60  # 30 dias
MIN_VOLUME_USD       = 100.0
MIN_BUYERS_24H       = 5
MIN_BUY_SELL_RATIO   = 1.0

REQUIRED_LINK_TYPES = {"twitter", "telegram", "website", "discord", "x"}
BLACKLIST_PATTERNS = [
    re.compile(r"\btest\b", re.I),
    re.compile(r"\brug\b", re.I),
    re.compile(r"\bscam\b", re.I),
    re.compile(r"\bairdrop\b", re.I),
    re.compile(r"\bpump\b", re.I),
    re.compile(r"\bdev\s+is\s+gone\b", re.I),
]

def _to_int(x, default=0) -> int:
    try:
        return int(x)
    except Exception:
        try:
            return int(float(x))
        except Exception:
            return default

def _to_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

# ---------- checks retornam True/False/None (desconhecido) ----------
def is_recent(t: Dict) -> Optional[bool]:
    try:
        age = (t.get("age") or {}).get("seconds")
        if age is None: return None
        return int(age) < MAX_TOKEN_AGE_SECONDS
    except:
        return None

def has_good_volume(t: Dict) -> Optional[bool]:
    v = (t.get("volume") or {}).get("h24")
    if v is None: return None
    return _to_float(v) > MIN_VOLUME_USD

def has_official_links(t: Dict) -> Optional[bool]:
    links = t.get("links") or []
    if links is None: return None
    for link in links:
        typ = (link.get("type") or link.get("label") or "").lower()
        if typ in REQUIRED_LINK_TYPES and link.get("url"):
            return True
    return False

def has_active_buyers(t: Dict) -> Optional[bool]:
    buys = ((t.get("txns") or {}).get("h24") or {}).get("buys")
    if buys is None: return None
    return _to_int(buys) >= MIN_BUYERS_24H

def has_good_buy_sell_ratio(t: Dict) -> Optional[bool]:
    h24 = (t.get("txns") or {}).get("h24") or {}
    buys = h24.get("buys"); sells = h24.get("sells")
    if buys is None and sells is None: return None
    buys = _to_int(buys, 0); sells = _to_int(sells, 0)
    if sells == 0:
        return True if buys > 0 else None
    return (buys / max(1, sells)) >= MIN_BUY_SELL_RATIO

def has_clean_description(t: Dict) -> Optional[bool]:
    desc = t.get("description")
    if desc is None: return None
    return not any(p.search(desc) for p in BLACKLIST_PATTERNS)

# ---------- avaliação principal ----------
def evaluate_token(t: Dict) -> Optional[Dict]:
    checks = {
        "idade":          is_recent(t),
        "volume":         has_good_volume(t),
        "links":          has_official_links(t),
        "compradores":    has_active_buyers(t),
        "buy_sell_ratio": has_good_buy_sell_ratio(t),
        "descricao":      has_clean_description(t),
    }
    passed   = [k for k,v in checks.items() if v is True]
    failed   = [k for k,v in checks.items() if v is False]
    unknown  = [k for k,v in checks.items() if v is None]

    # reprova se descrição suja
    if "descricao" in failed:
        status = "rejected"
    else:
        status = "ok" if len(passed) >= 3 else ("partial" if len(passed) >= 2 else "rejected")

    sym = t.get("symbol") or "???"
    age = (t.get("age") or {}).get("seconds")
    vol = (t.get("volume") or {}).get("h24")
    h24 = (t.get("txns") or {}).get("h24") or {}
    print(f"🔎 {sym}: idade={age} | volume=${vol} | buys={h24.get('buys')} | sells={h24.get('sells')} | "
          f"status={status} | passou={passed} | falhou={failed} | desconhecido={unknown}")

    if status == "rejected":
        return None

    # Anexa metadados de avaliação para a rota popular o seu modelo
    t["__eval__"] = {"status": status, "failed": failed}
    return t

def filter_tokens(tokens: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    for tk in tokens:
        r = evaluate_token(tk)
        if r:
            out.append(r)
    return out
