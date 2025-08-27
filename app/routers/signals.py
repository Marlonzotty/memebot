# app/routers/signals.py
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional, Tuple

from app.models.signal_model import Signal
from app.services.gpt_analysis import analyze_tokens

# --- EVM/Dex (opcional) ---
from app.services.dex_api import get_token_profiles
from app.utils.filters import (
    evaluate_token,       # pode anexar __eval__ ou retornar dict; tratamos os dois casos
    is_recent,
    has_good_volume,
    has_official_links,
    has_active_buyers,
    has_clean_description,
)

# --- Solana ---
from app.services.solscan_client import SolscanClient
from app.utils.solana_normalizer import (
    normalize_solscan_meta_to_snapshot,
    merge_birdeye_into_snapshot,
)
from app.services.birdeye_client import (
    BirdeyeClient,
    BirdeyeAuthOrPlanError,
)

router = APIRouter(prefix="/signals", tags=["signals"])

# ------------------------------
# Helpers locais
# ------------------------------
def normalize_chain_id(raw_chain) -> int:
    try:
        return int(raw_chain)
    except (ValueError, TypeError):
        mapping = {
            "ethereum": 1, "eth": 1,
            "bsc": 56, "bnb": 56,
            "solana": 101, "sol": 101,
            "base": 8453,
            "polygon": 137, "matic": 137,
            "arbitrum": 42161, "arb": 42161,
        }
        return mapping.get(str(raw_chain).lower(), -1)

def normalize_links(raw_links: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    normalized = []
    for link in (raw_links or []):
        type_ = (link.get("type") or link.get("label", "")).lower()
        url = link.get("url")
        if type_ in {"website", "twitter", "telegram", "discord"} and url:
            normalized.append({"type": type_, "url": url})
    return normalized

def _evm_eval_info(token: Dict[str, Any], evaluation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normaliza leitura de status/failed independente do formato de evaluate_token.
    - Se evaluate_token anexa __eval__ no token -> usamos __eval__
    - Se evaluate_token retorna dict com 'status'/'failed' -> usamos direto
    - Caso contrário -> defaults seguros
    """
    if isinstance(token.get("__eval__"), dict):
        ev = token["__eval__"]
        return {"status": ev.get("status", "ok"), "failed": ev.get("failed", [])}
    if isinstance(evaluation, dict):
        if "status" in evaluation or "failed" in evaluation:
            return {"status": evaluation.get("status", "ok"), "failed": evaluation.get("failed", [])}
    return {"status": "ok", "failed": []}

def _snapshot_to_signal_solana(snapshot: Dict[str, Any], *, chain_id: int = 101) -> Signal:
    links = normalize_links(snapshot.get("links") or [])
    classification = snapshot.get("classification")  # "high_potential" | "watchlist" | "discard" ...
    flags = list(snapshot.get("flags") or [])
    status = "ok" if classification in ("high_potential", "watchlist") else "partial"

    return Signal(
        tokenAddress = str(snapshot.get("tokenAddress") or ""),
        chainId      = int(chain_id),

        url         = snapshot.get("solscanUrl") or snapshot.get("dexscreenerUrl") or snapshot.get("birdeyeUrl") or snapshot.get("dextoolsUrl"),
        icon        = None,
        header      = snapshot.get("header") or snapshot.get("symbol") or snapshot.get("name"),
        description = snapshot.get("description"),
        links       = [{"type": l["type"], "url": l["url"]} for l in links],

        status = status,
        failed = flags,

        # Extras aceitos pelo modelo
        ageMinutes   = snapshot.get("ageMinutes"),
        liquidityUSD = snapshot.get("liquidityUSD"),
        mcapUSD      = snapshot.get("mcapUSD"),
        fdvUSD       = snapshot.get("fdvUSD"),
        volumeUSD_5m = snapshot.get("volumeUSD_5m"),
        volumeUSD_1h = snapshot.get("volumeUSD_1h"),
        volumeUSD_24h= snapshot.get("volumeUSD_24h"),
        score_local  = snapshot.get("score_local"),
        classification = classification,
        flags = flags,
    )

# ------------------------------
# /signals (principal)
# ------------------------------
@router.get("", response_model=List[Signal])   # /signals  (evita 307)
@router.get("/", response_model=List[Signal])  # /signals/
async def get_signals(
    analyze: bool = Query(False, description="Se true, qualifica com ChatGPT"),
    chain: str = Query("solana", description="solana | dex"),
    mints: Optional[str] = Query(None, description="Lista de mints separada por vírgula (quando chain=solana)"),
):
    """
    - chain=solana (padrão): exige ?mints=<mint1,mint2,...>. Enriquecimento com Birdeye e normalização Solscan.
    - chain=dex: usa get_token_profiles() + filtros locais.
    """
    chain_lower = (chain or "solana").lower()

    # ---------------- SOLANA ----------------
    if chain_lower in {"solana", "sol"}:
        if not mints:
            raise HTTPException(
                status_code=400,
                detail="Para chain=solana informe ?mints=m1,m2,... ou use /signals/solana/snapshot_enriched/{mint}"
            )
        mint_list = [m.strip() for m in mints.split(",") if m.strip()]
        if not mint_list:
            raise HTTPException(status_code=400, detail="Nenhum mint válido foi informado.")

        snapshots: List[Dict[str, Any]] = []
        signals: List[Signal] = []

        async with SolscanClient() as sol, BirdeyeClient() as be:
            print(f"🔍 Total mints recebidos: {len(mint_list)}")
            for mint in mint_list:
                try:
                    meta = await sol.token_meta(mint)
                    if not meta:
                        print(f"❌ Sem meta na Solscan para {mint}")
                        continue

                    snap = normalize_solscan_meta_to_snapshot(meta, mint)

                    overview, used_fallback = await be.overview_with_fallback(mint)
                    try:
                        volume = await be.token_volume_points(mint, interval="5m", limit=12)
                    except BirdeyeAuthOrPlanError:
                        volume = {"data": {"points": []}}
                    try:
                        trades5m = await be.token_trades_recent(mint, limit=100)
                    except BirdeyeAuthOrPlanError:
                        trades5m = {"data": {}}

                    snap = merge_birdeye_into_snapshot(snap, overview, volume, trades5m)
                    snap["birdeyeFallbackFromOverview"] = used_fallback
                    snapshots.append(snap)

                    sig = _snapshot_to_signal_solana(snap, chain_id=101)
                    signals.append(sig)
                    print(f"✅ SELECIONADO (SOL): {sig.header} — status={sig.status} — flags={sig.failed}")

                except Exception as e:
                    print(f"⚠️ Falha ao processar mint {mint}: {e}")

        # Análise opcional GPT em lote
        if analyze and snapshots:
            try:
                llm_out = analyze_tokens(snapshots)
                llm_map: Dict[str, Any] = {}
                for item in llm_out or []:
                    addr = item.get("tokenAddress")
                    if addr:
                        llm_map[addr] = item

                for i, sig in enumerate(signals):
                    item = llm_map.get(sig.tokenAddress, {})
                    signals[i].decision   = item.get("decision")
                    signals[i].confidence = item.get("confidence")
                    signals[i].rationale  = item.get("rationale")
            except Exception as e:
                print("⚠️ Falha na análise LLM (solana):", e)

        if not signals:
            print("⚠️ Nenhum token promissor encontrado (solana).")
            raise HTTPException(status_code=404, detail="Nada foi encontrado (solana).")
        return signals

    # ---------------- DEX (EVM/DexScreener) ----------------
    elif chain_lower == "dex":
        raw_data = get_token_profiles()
        results: List[Signal] = []
        approved_tokens: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []  # (token, evaluation)

        print(f"🔍 Total tokens recebidos (dex): {len(raw_data)}")

        for token in raw_data:
            evaluation = evaluate_token(token)
            if not evaluation:
                name = token.get("name") or token.get("symbol") or token.get("header") or token.get("tokenAddress") or "sem nome"
                erros = []
                if not is_recent(token): erros.append("idade")
                if not has_good_volume(token): erros.append("volume")
                if not has_official_links(token): erros.append("links")
                if not has_active_buyers(token): erros.append("compradores")
                if not has_clean_description(token): erros.append("descrição")
                print(f"❌ DESCARTADO: {name} — FALHOU EM: {', '.join(erros)}")
                continue

            ev_info = _evm_eval_info(token, evaluation)
            print(f"✅ SELECIONADO (DEX): {(token.get('name') or token.get('symbol') or token.get('header') or 'sem nome')} — "
                  f"STATUS: {ev_info['status']} — FALHOU EM: {ev_info['failed']}")
            approved_tokens.append((token, evaluation))

        if not approved_tokens:
            print("⚠️ Nenhum token promissor encontrado após aplicar os filtros (dex).")
            raise HTTPException(status_code=404, detail="Nada foi encontrado com os filtros aplicados (dex).")

        # 🔎 Análise opcional com LLM
        llm_map: Dict[str, Any] = {}
        if analyze:
            try:
                llm_out = analyze_tokens([t for (t, _) in approved_tokens])
                for item in llm_out or []:
                    addr = item.get("tokenAddress")
                    if addr:
                        llm_map[addr] = item
            except Exception as e:
                print("⚠️ Falha na análise LLM (dex):", e)

        # Monta payload final
        for token, evaluation in approved_tokens:
            addr = token.get("tokenAddress") or token.get("address") or ""
            llm = llm_map.get(addr, {}) if analyze else {}
            ev_info = _evm_eval_info(token, evaluation)

            results.append(Signal(
                tokenAddress = addr,
                url          = token.get("url"),
                icon         = token.get("icon"),
                header       = token.get("header") or token.get("name") or token.get("symbol"),
                description  = token.get("description"),
                chainId      = normalize_chain_id(token.get("chainId") or token.get("chain")),
                links        = normalize_links(token.get("links", [])),
                status       = ev_info["status"],
                failed       = ev_info["failed"],
                decision     = llm.get("decision"),
                confidence   = llm.get("confidence"),
                rationale    = llm.get("rationale"),
            ))

            print("🔬 DEBUG TOKEN (DEX):", {
                "address": addr,
                "decision": llm.get("decision"),
                "confidence": llm.get("confidence"),
                "rationale": llm.get("rationale"),
            })

        return results

    else:
        raise HTTPException(status_code=400, detail="Parâmetro 'chain' inválido. Use 'solana' ou 'dex'.")

# ------------------------------
# Solscan: meta e snapshot normalizado
# ------------------------------
@router.get("/solana/meta/{mint}")
async def solana_meta(mint: str):
    """
    Retorna metadados do token via Solscan.
    """
    async with SolscanClient() as cli:
        data = await cli.token_meta(mint)
        if not data:
            raise HTTPException(404, "Sem dados da Solscan")
        return data

@router.get("/solana/snapshot/{mint}")
async def solana_snapshot(mint: str):
    """
    Devolve um 'snapshot' NORMALIZADO (apenas Solscan).
    """
    async with SolscanClient() as cli:
        meta = await cli.token_meta(mint)
        if not meta:
            raise HTTPException(404, "Sem meta da Solscan")
        snapshot = normalize_solscan_meta_to_snapshot(meta, mint)
        return snapshot

# ------------------------------
# GPT: análise de um único mint (snapshot simples)
# ------------------------------
@router.get("/solana/analyze/{mint}")
async def solana_analyze(mint: str):
    async with SolscanClient() as cli:
        meta = await cli.token_meta(mint)
        if not meta:
            raise HTTPException(status_code=404, detail="Sem meta da Solscan")

        snapshot = normalize_solscan_meta_to_snapshot(meta, mint)

    try:
        llm_out = analyze_tokens([snapshot])  # lista
        llm_item = llm_out[0] if isinstance(llm_out, list) and llm_out else {}
    except Exception as e:
        print("⚠️ Falha na análise LLM (single):", e)
        llm_item = {}

    return {
        "snapshot": snapshot,
        "analysis": {
            "decision": llm_item.get("decision"),
            "confidence": llm_item.get("confidence"),
            "rationale": llm_item.get("rationale"),
            "scores": llm_item.get("scores"),
            "flags": llm_item.get("flags"),
        }
    }

# ------------------------------
# Snapshot ENRICHED (Solscan + Birdeye)
# ------------------------------
@router.get("/solana/snapshot_enriched/{mint}")
async def solana_snapshot_enriched(mint: str):
    """
    1) Solscan meta -> snapshot normalizado (tolerante ao plano)
    2) Birdeye overview (com fallback) + volume points (5m) + trades recentes
    3) merge_birdeye_into_snapshot -> score_local/flags/classification
    """

    snapshot = {}
    birdeye_status = {"overview": None, "volume": None, "trades": None}

    async with SolscanClient() as sol, BirdeyeClient() as be:
        # --- Solscan ---
        try:
            meta = await sol.token_meta(mint)
            snapshot = normalize_solscan_meta_to_snapshot(meta or {}, mint)
            if not meta:
                snapshot["solscanLimitedPlan"] = True
        except Exception as e:
            print(f"⚠️ Solscan meta falhou: {e}")
            snapshot = normalize_solscan_meta_to_snapshot({}, mint)
            snapshot["solscanError"] = str(e)

        # --- Birdeye: overview + fallback ---
        try:
            overview, used_fallback = await be.overview_with_fallback(mint)
            snapshot["birdeyeFallbackFromOverview"] = used_fallback
            birdeye_status["overview"] = "fallback" if used_fallback else "ok"
        except BirdeyeAuthOrPlanError as e:
            overview = {}
            birdeye_status["overview"] = f"unauthorized: {str(e)}"
        except Exception as e:
            overview = {}
            birdeye_status["overview"] = f"error: {type(e).__name__}"

        # --- Volume points ---
        try:
            volume = await be.token_volume_points(mint, interval="5m", limit=12)
            birdeye_status["volume"] = "ok"
        except BirdeyeAuthOrPlanError:
            volume = {"data": {"points": []}}
            birdeye_status["volume"] = "unauthorized"
        except Exception as e:
            volume = {"data": {"points": []}}
            birdeye_status["volume"] = f"error: {type(e).__name__}"

        # --- Trades recentes ---
        try:
            trades5m = await be.token_trades_recent(mint, limit=100)
            birdeye_status["trades"] = "ok"
        except BirdeyeAuthOrPlanError:
            trades5m = {"data": {}}
            birdeye_status["trades"] = "unauthorized"
        except Exception as e:
            trades5m = {"data": {}}
            birdeye_status["trades"] = f"error: {type(e).__name__}"

        # --- Merge final ---
        snapshot = merge_birdeye_into_snapshot(snapshot, overview, volume, trades5m)
        snapshot["birdeyeStatus"] = birdeye_status

    return snapshot

# ------------------------------
# GPT: análise sobre o enriched
# ------------------------------
@router.get("/solana/analyze_enriched/{mint}")
async def solana_analyze_enriched(mint: str):
    async with SolscanClient() as sol, BirdeyeClient() as be:
        # Meta tolerante
        try:
            meta = await sol.token_meta(mint)
        except Exception as e:
            print(f"⚠️ Solscan meta falhou: {e}")
            meta = {}

        snap = normalize_solscan_meta_to_snapshot(meta or {}, mint)

        overview, used_fallback = await be.overview_with_fallback(mint)
        try:
            volume = await be.token_volume_points(mint, interval="5m", limit=12)
        except BirdeyeAuthOrPlanError:
            volume = {"data": {"points": []}}
        try:
            trades5m = await be.token_trades_recent(mint, limit=100)
        except BirdeyeAuthOrPlanError:
            trades5m = {"data": {}}

        snap = merge_birdeye_into_snapshot(snap, overview, volume, trades5m)
        snap["birdeyeFallbackFromOverview"] = used_fallback

    try:
        llm_out = analyze_tokens([snap])
        llm_item = llm_out[0] if isinstance(llm_out, list) and llm_out else {}
    except Exception as e:
        print("⚠️ Falha na análise LLM (enriched):", e)
        llm_item = {}

    return {"snapshot": snap, "analysis": llm_item}
