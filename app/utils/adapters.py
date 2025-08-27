# app/utils/adapters.py
from typing import Dict, Any, List
from app.models.signal_model import Signal, Link

def solana_snapshot_to_signal(snapshot: Dict[str, Any], *, chain_id: int = 101) -> Signal:
    """
    Converte um snapshot produzido por:
      - normalize_solscan_meta_to_snapshot(...)
      - merge_birdeye_into_snapshot(...)
    em um objeto Signal pronto para resposta da API.
    """

    # Links (garante types/urls válidos)
    links_raw = snapshot.get("links") or []
    links: List[Link] = []
    for l in links_raw:
        url = (l or {}).get("url")
        if url:
            links.append(Link(type=str((l or {}).get("type") or ""), url=str(url)))

    # Status/failed: usa flags/classification do scoring local
    flags = list(snapshot.get("flags") or [])
    classification = snapshot.get("classification")  # "high_potential" | "watchlist" | "discard" ...
    status = "ok" if classification in ("high_potential", "watchlist") else "partial"

    return Signal(
        # Identificação
        tokenAddress = str(snapshot.get("tokenAddress") or ""),
        chainId      = int(chain_id),

        # Exibição
        url         = snapshot.get("solscanUrl") or snapshot.get("dexscreenerUrl") or snapshot.get("birdeyeUrl") or snapshot.get("dextoolsUrl"),
        icon        = None,
        header      = snapshot.get("header") or snapshot.get("symbol") or snapshot.get("name"),
        description = snapshot.get("description"),
        links       = links,

        # Avaliação
        status = status,
        failed = flags,

        # Extras úteis (mantemos se existirem no snapshot)
        name        = snapshot.get("name"),
        symbol      = snapshot.get("symbol"),
        ageMinutes  = snapshot.get("ageMinutes"),
        liquidityUSD= snapshot.get("liquidityUSD"),
        mcapUSD     = snapshot.get("mcapUSD"),
        fdvUSD      = snapshot.get("fdvUSD"),
        volumeUSD_5m= snapshot.get("volumeUSD_5m"),
        volumeUSD_1h= snapshot.get("volumeUSD_1h"),
        volumeUSD_24h= snapshot.get("volumeUSD_24h"),
        score_local = snapshot.get("score_local"),
        classification = classification,
        flags = flags,
    )
