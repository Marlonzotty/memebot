# app/models/signal_model.py
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Link(BaseModel):
    type: str
    url: str


class Signal(BaseModel):
    # Identificação principal
    tokenAddress: str
    chainId: int = Field(..., description="Chain ID (EVM) ou ID fixo (ex.: 101 p/ Solana ou 0 como sentinela)")

    # Infos de exibição
    url: Optional[str] = None
    icon: Optional[str] = None
    header: Optional[str] = None
    description: Optional[str] = None
    links: List[Link] = Field(default_factory=list)

    # Estado da avaliação (pipeline local)
    status: Optional[str] = "ok"                       # "ok" | "partial"
    failed: List[str] = Field(default_factory=list)    # critérios não atendidos

    # 🔽 Campos opcionais p/ decisão externa (GPT/Agent)
    decision: Optional[str] = None                     # "entrada" | "observar" | "evitar"
    confidence: Optional[float] = None                 # 0–100
    rationale: Optional[str] = None                    # explicação curta

    # 🔽 Extras comuns (Solana/EVM)
    name: Optional[str] = None
    symbol: Optional[str] = None

    # Tempo/idade
    ageMinutes: Optional[int] = None                   # Solana
    ageSeconds: Optional[int] = None                   # EVM/DexScreener

    # Preço e liquidez
    priceUSD: Optional[float] = None
    liquidityUSD: Optional[float] = None
    mcapUSD: Optional[float] = None
    fdvUSD: Optional[float] = None

    # Volume (janelas diferentes)
    volumeUSD_5m: Optional[float] = None
    volumeUSD_1h: Optional[float] = None
    volumeUSD_24h: Optional[float] = None
    volumeH24: Optional[float] = None                  # alias prático p/ DexScreener (== volumeUSD_24h)

    # Transações / fluxo de ordens
    txnsBuy_5m: Optional[int] = None
    txnsSell_5m: Optional[int] = None
    buyers_5m: Optional[int] = None
    sellers_5m: Optional[int] = None
    txnsBuy_24h: Optional[int] = None
    txnsSell_24h: Optional[int] = None
    buySellRatio_24h: Optional[float] = None

    # Scoring local / flags
    score_local: Optional[float] = None
    classification: Optional[str] = None
    flags: List[str] = Field(default_factory=list)

    # ---------------------------
    # FÁBRICAS DE CONVERSÃO
    # ---------------------------
    @classmethod
    def from_solana_snapshot(cls, snap: Dict[str, Any], *, chain_id: int = 101) -> "Signal":
        """
        Converte o snapshot vindo do seu solana_normalizer + merges do Birdeye.
        """
        links_raw = snap.get("links") or []
        links = [Link(type=str(l.get("type") or ""), url=str(l.get("url"))) for l in links_raw if l.get("url")]

        # status/failed opcionais via flags/classification locais
        status = "ok"
        failed = list(snap.get("flags") or [])
        if snap.get("classification") == "discard":
            status = "partial" if failed else "partial"

        return cls(
            tokenAddress = str(snap.get("tokenAddress") or ""),
            chainId      = int(chain_id),
            url          = snap.get("solscanUrl") or snap.get("dexscreenerUrl") or snap.get("dextoolsUrl") or snap.get("birdeyeUrl"),
            icon         = None,
            header       = snap.get("header") or snap.get("symbol") or snap.get("name"),
            description  = snap.get("description"),
            links        = links,

            status       = status,
            failed       = failed,

            # básicos
            name         = snap.get("name"),
            symbol       = snap.get("symbol"),

            # tempo
            ageMinutes   = snap.get("ageMinutes"),
            ageSeconds   = None,

            # preço/liq/caps
            priceUSD     = snap.get("priceUSD"),
            liquidityUSD = snap.get("liquidityUSD"),
            mcapUSD      = snap.get("mcapUSD"),
            fdvUSD       = snap.get("fdvUSD"),

            # volumes
            volumeUSD_5m  = snap.get("volumeUSD_5m"),
            volumeUSD_1h  = snap.get("volumeUSD_1h"),
            volumeUSD_24h = snap.get("volumeUSD_24h"),
            volumeH24     = snap.get("volumeUSD_24h"),

            # fluxo ordens
            txnsBuy_5m   = snap.get("txnsBuy_5m"),
            txnsSell_5m  = snap.get("txnsSell_5m"),
            buyers_5m    = snap.get("buyers_5m"),
            sellers_5m   = snap.get("sellers_5m"),
            txnsBuy_24h  = None,
            txnsSell_24h = None,
            buySellRatio_24h = None,

            # score/flags
            score_local     = snap.get("score_local"),
            classification  = snap.get("classification"),
            flags           = list(snap.get("flags") or []),
        )

    @classmethod
    def from_evm_normalized(cls, t: Dict[str, Any]) -> "Signal":
        """
        Converte um token já normalizado do seu normalize.py (DexScreener/EVM).
        Espera chaves: tokenAddress, chainId, url, icon, header, description, links[],
        age.seconds, volume.h24, txns.h24.{buys,sells}, liquidity.usd, name/symbol.
        Pode ler avaliação em t["__eval__"] (status/failed).
        """
        links_raw = t.get("links") or []
        links = [Link(type=str(l.get("type") or ""), url=str(l.get("url"))) for l in links_raw if l.get("url")]

        ev = t.get("__eval__") or {}
        buys24 = (((t.get("txns") or {}).get("h24") or {}).get("buys"))
        sells24 = (((t.get("txns") or {}).get("h24") or {}).get("sells"))
        try:
            ratio24 = (float(buys24) / float(sells24)) if sells24 and float(sells24) > 0 else (float(buys24) if buys24 else None)
        except Exception:
            ratio24 = None

        return cls(
            tokenAddress = str(t.get("tokenAddress") or t.get("address") or ""),
            chainId      = int(t.get("chainId") or 0),

            url          = t.get("url"),
            icon         = t.get("icon"),
            header       = t.get("header") or t.get("name") or t.get("symbol"),
            description  = t.get("description"),
            links        = links,

            status       = ev.get("status", "ok"),
            failed       = list(ev.get("failed") or []),

            name         = t.get("name"),
            symbol       = t.get("symbol"),

            ageMinutes   = None,
            ageSeconds   = (t.get("age") or {}).get("seconds"),

            priceUSD     = t.get("price_usd") or t.get("priceUSD"),
            liquidityUSD = (t.get("liquidity") or {}).get("usd"),
            mcapUSD      = t.get("mcapUSD"),
            fdvUSD       = t.get("fdvUSD"),

            volumeUSD_24h = (t.get("volume") or {}).get("h24"),
            volumeH24     = (t.get("volume") or {}).get("h24"),

            txnsBuy_24h  = buys24 if isinstance(buys24, int) else None,
            txnsSell_24h = sells24 if isinstance(sells24, int) else None,
            buySellRatio_24h = ratio24,

            # campos 5m/1h podem não existir em EVM
            volumeUSD_5m  = t.get("volumeUSD_5m"),
            volumeUSD_1h  = t.get("volumeUSD_1h"),
            txnsBuy_5m    = t.get("txnsBuy_5m"),
            txnsSell_5m   = t.get("txnsSell_5m"),
            buyers_5m     = t.get("buyers_5m"),
            sellers_5m    = t.get("sellers_5m"),

            score_local     = t.get("score_local"),
            classification  = t.get("classification"),
            flags           = list(t.get("flags") or []),
        )

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
