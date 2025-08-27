# app/services/solscan_client.py
import os
from typing import Optional, Tuple, Dict, Any
import httpx

SOLSCAN_API_KEY = os.getenv("SOLSCAN_API_KEY", "")
SOLSCAN_BASE = os.getenv("SOLSCAN_BASE", "https://pro-api.solscan.io").rstrip("/")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
TIMEOUT = float(os.getenv("TIMEOUT", "15"))

def _unwrap(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Se vier no formato {"success":true,"data":{...}}, retorna só o 'data'."""
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload if isinstance(payload, dict) else {}

class SolscanClient:
    def __init__(self, timeout: Optional[float] = None):
        headers = {"token": SOLSCAN_API_KEY} if SOLSCAN_API_KEY else {}
        self._client: Optional[httpx.AsyncClient] = httpx.AsyncClient(
            timeout=timeout or TIMEOUT,
            headers=headers
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_json(self, url: str, params: dict) -> Tuple[int, Dict[str, Any]]:
        if self._client is None:
            headers = {"token": SOLSCAN_API_KEY} if SOLSCAN_API_KEY else {}
            self._client = httpx.AsyncClient(timeout=TIMEOUT, headers=headers)
        r = await self._client.get(url, params=params)
        status = r.status_code
        try:
            data = r.json() if r.text else {}
        except Exception:
            data = {"raw": r.text}
        return status, data

    async def token_meta(self, mint: str, *, strict: bool = False) -> Dict[str, Any]:
        """
        Retorna SEMPRE um dict “plano” (sem wrapper) com meta do token.
        Se sua chave não tiver acesso (401/404), devolve {} em modo não-estrito.
        """
        if DRY_RUN:
            return {
                "mint": mint,
                "symbol": "MOCK",
                "holder": 321,
                "website": "https://example.org",
                "created_time": 1723500000,
                "mint_authority": None,
                "freeze_authority": None,
            }

        # Tentativa v2.0
        url_v2 = f"{SOLSCAN_BASE}/v2.0/token/meta"
        status, raw = await self._get_json(url_v2, {"address": mint})
        if status == 200:
            return _unwrap(raw)
        if status in (401, 404):
            if strict:
                msg = (raw.get("error_message") if isinstance(raw, dict) else None) or str(status)
                raise RuntimeError(f"Solscan v2.0 {status}: {msg}")

        # Fallback v1.0
        url_v1 = f"{SOLSCAN_BASE}/v1.0/token/meta"
        status2, raw2 = await self._get_json(url_v1, {"tokenAddress": mint})
        if status2 == 200:
            return _unwrap(raw2)
        if status2 in (401, 404):
            if strict:
                msg = (raw2.get("error_message") if isinstance(raw2, dict) else None) or str(status2)
                raise RuntimeError(f"Solscan v1.0 {status2}: {msg}")

        # Sem acesso a nenhum meta -> retorna vazio (para o normalizer lidar)
        return {}
