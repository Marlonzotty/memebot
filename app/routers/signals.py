# app/routers/signals.py
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict
from app.models.signal_model import Signal
from app.services.dex_api import get_token_profiles
from app.services.gpt_analysis import analyze_tokens  # 👈 NOVO
from app.utils.filters import (
    evaluate_token,
    is_recent,
    has_good_volume,
    has_official_links,
    has_active_buyers,
    has_clean_description,
)

router = APIRouter(prefix="/signals", tags=["signals"])

def normalize_chain_id(raw_chain):
    try:
        return int(raw_chain)
    except (ValueError, TypeError):
        mapping = {
            "ethereum": 1, "bsc": 56, "solana": 101, "base": 8453,
            "polygon": 137, "arbitrum": 42161,
        }
        return mapping.get(str(raw_chain).lower(), -1)

def normalize_links(raw_links):
    normalized = []
    for link in raw_links:
        type_ = link.get("type") or link.get("label", "").lower()
        url = link.get("url")
        if type_ in {"website", "twitter", "telegram"} and url:
            normalized.append({"type": type_, "url": url})
    return normalized

@router.get("/", response_model=List[Signal])
async def get_signals(analyze: bool = Query(False, description="Se true, qualifica com ChatGPT")):
    raw_data = get_token_profiles()
    results: List[Signal] = []
    approved_tokens: List[Dict] = []

    print(f"🔍 Total tokens recebidos: {len(raw_data)}")

    for token in raw_data:
        evaluation = evaluate_token(token)
        if not evaluation:
            name = token.get("name") or token.get("symbol") or token.get("tokenAddress") or "sem nome"
            erros = []
            if not is_recent(token): erros.append("idade")
            if not has_good_volume(token): erros.append("volume")
            if not has_official_links(token): erros.append("links")
            if not has_active_buyers(token): erros.append("compradores")
            if not has_clean_description(token): erros.append("descrição")
            print(f"❌ DESCARTADO: {name} — FALHOU EM: {', '.join(erros)}")
            continue

        print(f"✅ SELECIONADO: {token.get('name', 'sem nome')} — STATUS: {evaluation['status']} — FALHOU EM: {evaluation['failed']}")
        approved_tokens.append(token)

    if not approved_tokens:
        print("⚠️ Nenhum token promissor encontrado após aplicar os filtros.")
        raise HTTPException(status_code=404, detail="Nada foi encontrado com os filtros aplicados.")

    # 🔎 Análise opcional com LLM
    llm_map = {}
    if analyze:
        try:
            llm_out = analyze_tokens(approved_tokens)
            # Indexa por tokenAddress
            for item in llm_out:
                addr = item.get("tokenAddress")
                if addr:
                    llm_map[addr] = item
        except Exception as e:
            print("⚠️ Falha na análise LLM:", e)

    # Monta o payload final
    for token in approved_tokens:
        token_data = token.copy()
        addr = token_data.get("tokenAddress")
        llm = llm_map.get(addr, {}) if analyze else {}

        # Recalcula a avaliação local para obter status/failed sem mudar a estrutura acima
        evaluation = evaluate_token(token) or {"status": "unknown", "failed": []}

        signal = Signal(
            tokenAddress=token_data.get("tokenAddress"),
            url=token_data.get("url"),
            icon=token_data.get("icon"),
            header=token_data.get("header"),
            description=token_data.get("description"),
            chainId=normalize_chain_id(token_data.get("chainId")),
            links=normalize_links(token_data.get("links", [])),
            status=evaluation["status"],
            failed=evaluation["failed"],
            # Campos da análise LLM (se analyze=true)
            decision=llm.get("decision"),
            confidence=llm.get("confidence"),
            rationale=llm.get("rationale"),
        )
        results.append(signal)

        print("🔬 DEBUG TOKEN:", {
            "address": token_data.get("tokenAddress"),
            "decision": llm.get("decision"),
            "confidence": llm.get("confidence"),
            "rationale": llm.get("rationale"),
        })


    return results
