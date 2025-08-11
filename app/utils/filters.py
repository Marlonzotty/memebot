from typing import Dict, Optional, List
import re
from app.services.dex_api import get_token_profiles

# ---------------------- Parâmetros configuráveis ---------------------- #
MAX_TOKEN_AGE_SECONDS = 30 * 24 * 60 * 60  # 30 dias
MIN_VOLUME_USD = 100
MIN_BUYERS_24H = 0
MIN_BUY_SELL_RATIO = 1.0

REQUIRED_LINK_TYPES = {"twitter", "telegram", "website"}
BLACKLIST_PATTERNS = [
    re.compile(r"\btest\b", re.I),
    re.compile(r"\brug\b", re.I),
    re.compile(r"\bscam\b", re.I),
    re.compile(r"\bairdrop\b", re.I),
    re.compile(r"\bpump\b", re.I),
    re.compile(r"\bdev\s+is\s+gone\b", re.I),
]

# ---------------------- Funções de checagem ---------------------- #
def is_recent(token: Dict) -> bool:
    try:
        age = int(token.get("age", {}).get("seconds", 99999999))
        return age < MAX_TOKEN_AGE_SECONDS
    except:
        return False

def has_good_volume(token: Dict) -> bool:
    try:
        return float(token.get("volume", {}).get("h24", 0)) > MIN_VOLUME_USD
    except:
        return False

def has_official_links(token: Dict) -> bool:
    try:
        links = token.get("links", [])
        return any(link.get("type", "").lower() in REQUIRED_LINK_TYPES for link in links)
    except:
        return False

def has_active_buyers(token: Dict) -> bool:
    try:
        return int(token.get("txns", {}).get("h24", {}).get("buys", 0)) >= MIN_BUYERS_24H
    except:
        return False

def has_good_buy_sell_ratio(token: Dict) -> bool:
    try:
        buys = int(token.get("txns", {}).get("h24", {}).get("buys", 0))
        sells = int(token.get("txns", {}).get("h24", {}).get("sells", 1))  # evita divisão por zero
        return (buys / sells) >= MIN_BUY_SELL_RATIO
    except:
        return False

def has_clean_description(token: Dict) -> bool:
    try:
        description = (token.get("description") or "")
        return not any(pattern.search(description) for pattern in BLACKLIST_PATTERNS)
    except:
        return False

# ---------------------- Avaliação principal ---------------------- #
def evaluate_token(token: Dict) -> Optional[Dict]:
    checks = {
        "idade": is_recent(token),
        "volume": has_good_volume(token),
        "links": has_official_links(token),
        "compradores": has_active_buyers(token),
        "buy_sell_ratio": has_good_buy_sell_ratio(token),
        "descricao": has_clean_description(token),
    }

    passed = [k for k, v in checks.items() if v]
    failed = [k for k, v in checks.items() if not v]

    status = "ok" if len(passed) == len(checks) else "partial" if len(passed) >= 3 else "rejected"

    print(
        f"🔎 {token.get('symbol', '???')}: idade={token.get('age', {}).get('seconds')}s | "
        f"volume=${token.get('volume', {}).get('h24')} | "
        f"buys={token.get('txns', {}).get('h24', {}).get('buys')} | "
        f"sells={token.get('txns', {}).get('h24', {}).get('sells')} | "
        f"status={status} | falhou em: {failed}"
    )

    if status == "rejected":
        return None

    return {
        "status": status,
        "passed": passed,
        "failed": failed,
        "token": {
            "symbol": token.get("symbol"),
            "name": token.get("name"),
            "address": token.get("address"),
            "chain": token.get("chainId"),
            "age_sec": token.get("age", {}).get("seconds"),
            "volume_usd": token.get("volume", {}).get("h24"),
            "buys": token.get("txns", {}).get("h24", {}).get("buys", 0),
            "sells": token.get("txns", {}).get("h24", {}).get("sells", 0),
            "links": token.get("links", []),
            "description": token.get("description", ""),
        },
    }

def filter_tokens(tokens: List[Dict]) -> List[Dict]:
    return [result for token in tokens if (result := evaluate_token(token))]

# ---------------------- Função final de entrada ---------------------- #
def get_filtered_token_profiles() -> List[Dict]:
    raw_tokens = get_token_profiles()
    return filter_tokens(raw_tokens)
