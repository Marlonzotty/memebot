# app/services/gpt_analysis.py
import os
import re
import json
from typing import List, Dict, Any
from dotenv import load_dotenv

# Carrega .env localmente (não usado no Render, mas útil em dev)
load_dotenv()

ESSENTIAL_FIELDS = [
    "tokenAddress", "url", "header", "description", "chainId", "links",
]

def _get_openai_client():
    """Cria o client só quando necessário e via variável de ambiente."""
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY não definida. "
            "Defina no .env (dev) ou nas Environment Variables do Render."
        )
    return OpenAI(api_key=api_key)

def _compact_token(token: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: token.get(k) for k in ESSENTIAL_FIELDS if k in token}
    out["chainId"] = str(out.get("chainId", "")).lower()
    out["links"] = [
        {"type": (l.get("type") or l.get("label", "")).lower(), "url": l.get("url")}
        for l in (out.get("links") or [])
        if l.get("url")
    ]
    desc = (out.get("description") or "").strip()
    out["description"] = desc[:800]
    return out

SYSTEM_PROMPT = """Você é um analista quantitativo sênior focado em memecoins.
Tarefa: classificar cada token como UMA das opções: "entrada", "observar", "evitar".
Restrições:
- Seja conservador se faltar dados essenciais (links oficiais, liquidez/volume, histórico).
- Penalize tokens sem website/telegram/twitter oficiais.
- Considere risco de honeypot/phony caso descrição seja vaga ou exagerada.
- NÃO alucine dados não fornecidos.

Retorno em JSON estrito: lista de objetos com:
{
  "tokenAddress": "string",
  "decision": "entrada" | "observar" | "evitar",
  "confidence": 0-100,
  "rationale": "explicação curta e objetiva (<= 500 chars)"
}
"""

USER_TEMPLATE = """Analise os tokens abaixo. Critérios práticos:
- Liquidez mínima razoável p/ execução (quando informada). Falta de liquidez => "evitar" ou "observar".
- Volume/atividade (quando informado) => tendência e capacidade de saída.
- Links oficiais (site, twitter, telegram) => sinal de seriedade.
- Conteúdo da descrição: evitar hype vazio ou promessas grandiosas.

Tokens:
{compact_json}

Responda SOMENTE o JSON pedido, sem textos adicionais, sem markdown, sem ```json.
"""

def _parse_llm_json(text: str):
    if not text:
        raise ValueError("Resposta vazia da LLM")

    t = text.strip()

    # Remove cercas ``` ou ```json
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.IGNORECASE | re.DOTALL).strip()

    # Tentativa direta
    try:
        return json.loads(t)
    except Exception:
        pass

    # Extrai primeiro ARRAY completo
    m = re.search(r"\[[\s\S]*\]", t)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    # Extrai primeiro OBJETO completo
    m = re.search(r"\{[\s\S]*\}", t)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    raise ValueError("Não foi possível extrair JSON válido da resposta do LLM.")

def analyze_tokens(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recebe tokens e adiciona análise do GPT diretamente neles."""
    if not tokens:
        return []

    client = _get_openai_client()
    compacted = [_compact_token(t) for t in tokens]
    BATCH = 8
    results: List[Dict[str, Any]] = []

    for i in range(0, len(compacted), BATCH):
        batch = compacted[i:i + BATCH]
        user_msg = USER_TEMPLATE.format(compact_json=json.dumps(batch, ensure_ascii=False))

        try:
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0.2,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )

            text = (response.choices[0].message.content or "").strip()
            parsed = _parse_llm_json(text)

            if isinstance(parsed, list):
                results.extend(parsed)
            else:
                raise ValueError("Formato de resposta inesperado (esperado lista JSON).")

        except Exception as e:
            print("[GPT ERROR]", str(e))
            print("[GPT INPUT]", user_msg[:1500])
            if 'text' in locals():
                print("[GPT RAW OUTPUT]", repr(text[:1000]))
            for t in batch:
                results.append({
                    "tokenAddress": t.get("tokenAddress"),
                    "decision": "observar",
                    "confidence": 35,
                    "rationale": "Falha ao interpretar saída do LLM; usar avaliação local."
                })

    # Junta os campos do GPT com os tokens originais
    result_map = {r.get("tokenAddress"): r for r in results if r and r.get("tokenAddress")}
    for t in tokens:
        r = result_map.get(t.get("tokenAddress"))
        if r:
            t.update(r)

    return tokens
