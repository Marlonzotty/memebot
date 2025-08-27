# app/routers/links.py
from fastapi import APIRouter
from typing import Any, Dict
from app.services.birdeye_client import BirdeyeClient

router = APIRouter(prefix="/signals/solana", tags=["signals:solana"])

@router.get("/links/{mint}")
async def links_for_mint(mint: str) -> Dict[str, Any]:
    async with BirdeyeClient() as be:
        pairs = await be.token_pairs(mint)
        price = await be.price(mint, include_liquidity=True)

    return {
        "tokenAddress": mint,
        "birdeyeUrl": f"https://birdeye.so/token/{mint}?chain=solana",
        "solscanUrl": f"https://solscan.io/token/{mint}",
        "pairs_raw": pairs.get("data"),
        "price_raw": price.get("data"),
    }
