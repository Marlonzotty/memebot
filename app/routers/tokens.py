from fastapi import APIRouter
from app.services.CoinGeckoService import CoinGeckoService
from app.models.signal_model import Signal

router = APIRouter(prefix="/token", tags=["tokens"])

@router.get("/{token_address}", response_model=Signal)
async def get_token_data(token_address: str):
    coingecko_data = CoinGeckoService.get_token_data_from_coingecko(token_address)
    
    if not coingecko_data:
        return Signal(
            tokenAddress=token_address,
            chainId=101,
            status="partial",
            failed=["Erro ao buscar dados da CoinGecko"]
        )

    snap = {
        "tokenAddress": token_address,
        "priceUSD": coingecko_data.get("priceUSD"),
        "mcapUSD": coingecko_data.get("mcapUSD"),
        "volumeUSD_24h": coingecko_data.get("volumeUSD_24h"),
        "birdeyeUrl": coingecko_data.get("url"),
        "icon": coingecko_data.get("icon"),
        "links": [{"type": "coingecko", "url": coingecko_data.get("url")}] if coingecko_data.get("url") else [],
        "name": coingecko_data.get("name"),
        "symbol": coingecko_data.get("symbol"),
        "header": coingecko_data.get("symbol") or coingecko_data.get("name"),
        "description": None,
        "flags": [],
        "classification": None,
        "score_local": None,
    }

    signal = Signal.from_solana_snapshot(snap, chain_id=101)
    return signal