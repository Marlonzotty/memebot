import os
import asyncio
import random
from typing import Any, Dict, Optional, Tuple
import httpx

# Configurações globais
BIRDEYE_BASE_URL = os.getenv("BIRDEYE_BASE_URL", "https://public-api.birdeye.so").rstrip("/")
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "").strip()
BIRDEYE_DRY_RUN = os.getenv("BIRDEYE_DRY_RUN", "false").lower() == "true"  # 🔄 por padrão, DRY_RUN é false

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "10"))
HTTP_MAX_RETRIES = int(os.getenv("HTTP_MAX_RETRIES", "5"))

RETRIABLE_STATUS = {429, 500, 502, 503, 504}

# Exceções personalizadas
class BirdeyeError(Exception):
    pass

class BirdeyeAuthOrPlanError(BirdeyeError):
    """Erro 401 ou 403 (plano insuficiente ou chave inválida)"""

class BirdeyeClient:
    """
    Cliente Birdeye com:
    - Headers com API key
    - Retry com backoff exponencial
    - Fallback de overview -> price
    - Suporte a uso com ou sem 'async with'
    """

    def __init__(self,
                 base_url: str = BIRDEYE_BASE_URL,
                 api_key: str = BIRDEYE_API_KEY,
                 timeout: float = HTTP_TIMEOUT):
        if not api_key and not BIRDEYE_DRY_RUN:
            raise ValueError("BIRDEYE_API_KEY não definido")
        
        self._base = base_url.rstrip("/")
        self._headers = {"X-API-KEY": api_key, "accept": "application/json"}
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self._timeout, headers=self._headers)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()

    async def aclose(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout, headers=self._headers)

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if BIRDEYE_DRY_RUN:
            return {"data": {}, "dry_run": True}

        await self._ensure_client()
        url = f"{self._base}{path}"
        backoff = 0.5

        for _ in range(HTTP_MAX_RETRIES):
            r = await self._client.get(url, params=params or {})
            s = r.status_code

            if s == 200:
                try:
                    return r.json()
                except Exception as e:
                    raise BirdeyeError(f"JSON inválido em {path}: {e}. body[:300]={r.text[:300]}")

            if s in (401, 403):
                raise BirdeyeAuthOrPlanError(f"{path} -> {s}: {r.text[:300]}")

            if s in RETRIABLE_STATUS:
                jitter = random.uniform(0.0, 0.25)
                await asyncio.sleep(backoff + jitter)
                backoff = min(backoff * 2, 4.0)
                continue

            raise BirdeyeError(f"{path} -> {s}: {r.text[:300]}")

        raise BirdeyeError(f"{path} -> retries esgotados")

    # --- Endpoints públicos ---
    async def networks(self) -> Dict[str, Any]:
        return await self._get("/defi/networks")

    async def price(self, mint: str, include_liquidity: bool = True, chain: str = "solana") -> Dict[str, Any]:
        return await self._get("/defi/price", {
            "address": mint,
            "chain": chain,
            "include_liquidity": "true" if include_liquidity else "false",
        })

    async def token_overview(self, mint: str, chain: str = "solana") -> Dict[str, Any]:
        return await self._get("/defi/token_overview", {"address": mint, "chain": chain})

    async def token_volume_points(self, mint: str, interval: str = "5m", limit: int = 12, chain: str = "solana") -> Dict[str, Any]:
        return await self._get("/defi/history/market-trades", {
            "address": mint, "chain": chain, "type": interval, "limit": limit
        })

    async def token_trades_recent(self, mint: str, limit: int = 100, chain: str = "solana") -> Dict[str, Any]:
        return await self._get("/defi/token_trades_recent", {
            "address": mint, "chain": chain, "limit": limit
        })

    async def token_pairs(self, mint: str, chain: str = "solana") -> Dict[str, Any]:
        return await self._get("/defi/token_pair", {"address": mint, "chain": chain})

    # --- Helper com fallback seguro ---
    async def overview_with_fallback(self, mint: str, chain: str = "solana") -> Tuple[Dict[str, Any], bool]:
        """
        Retorna: (dados, usou_fallback)
        """
        try:
            data = await self.token_overview(mint, chain=chain)
            return data, False
        except BirdeyeAuthOrPlanError:
            try:
                data = await self.price(mint, include_liquidity=True, chain=chain)
                return data, True
            except BirdeyeError:
                raise  # Propaga erro de fallback também
