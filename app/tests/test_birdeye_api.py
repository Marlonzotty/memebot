import os
import asyncio
import pytest
import httpx

BASE_URL = os.getenv("BIRDEYE_BASE_URL", "https://public-api.birdeye.so")
API_KEY = os.getenv("BIRDEYE_API_KEY")
WSOL = "So11111111111111111111111111111111111111112"  # mint do wSOL

pytestmark = pytest.mark.asyncio

def _headers():
    return {"X-API-KEY": API_KEY, "accept": "application/json"}

async def _get(path: str, params=None, retries=3, timeout=10.0):
    """
    GET com retry/backoff simples para 429/5xx e erro detalhado nos demais.
    """
    url = f"{BASE_URL.rstrip('/')}{path}"
    backoff = 0.5
    async with httpx.AsyncClient(timeout=timeout) as client:
        for _ in range(retries):
            r = await client.get(url, params=params or {}, headers=_headers())
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 4.0)
                continue
            pytest.fail(f"{path} -> {r.status_code} body={r.text[:300]}")
        pytest.fail(f"{path} -> retries esgotados (último status={r.status_code}, body={r.text[:300]})")

@pytest.mark.skipif(not API_KEY, reason="BIRDEYE_API_KEY ausente")
async def test_birdeye_networks_endpoint():
    """
    /defi/networks deve retornar uma lista e conter 'solana'.
    Aceita lista de strings OU lista de dicts.
    """
    r = await _get("/defi/networks")
    data = r.json()
    assert "data" in data, f"sem 'data' no body: {data}"
    items = data["data"]
    assert isinstance(items, list), f"data['data'] não é lista: {type(items)} / body={data}"

    normalized = []
    for n in items:
        if isinstance(n, str):
            normalized.append(n.lower())
        elif isinstance(n, dict):
            for k in ("network", "name", "id"):
                if k in n and isinstance(n[k], str):
                    normalized.append(n[k].lower())
                    break

    assert any(s in ("solana", "sol") for s in normalized), f"solana não encontrada. items={items}"

@pytest.mark.skipif(not API_KEY, reason="BIRDEYE_API_KEY ausente")
async def test_price_endpoint_wsol():
    """
    /defi/price para wSOL: smoke test — deve retornar 'data' (dict).
    """
    r = await _get("/defi/price", {"address": WSOL, "chain": "solana", "include_liquidity": "true"})
    data = r.json()
    assert "data" in data and isinstance(data["data"], dict), f"body={data}"
    assert len(data["data"]) >= 1, f"data vazio: {data}"

@pytest.mark.skipif(not API_KEY, reason="BIRDEYE_API_KEY ausente")
async def test_token_overview_wsol():
    """
    /defi/token_overview:
      - 200 -> valida payload
      - 401 -> pula (plano sem acesso)
      - 429 -> pula (rate limit atingido)
    """
    url = f"{BASE_URL.rstrip('/')}/defi/token_overview"
    params = {"address": WSOL, "chain": "solana"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, params=params, headers=_headers())

    if r.status_code in (401, 429):
        pytest.skip(f"endpoint indisponível agora ({r.status_code}): {r.text[:200]}")

    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"

    data = r.json()
    assert "data" in data and isinstance(data["data"], dict), f"body={data}"
    keys = set(data["data"].keys())
    expect_any = {"liquidity", "market_cap", "fdv", "volume_24h_quote", "symbol", "price"}
    assert keys & expect_any, f"chaves inesperadas: {keys} / body={data}"
