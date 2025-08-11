# app/models/signal_model.py
from typing import List, Optional
from pydantic import BaseModel

class Link(BaseModel):
    type: str
    url: str

class Signal(BaseModel):
    tokenAddress: str
    url: str
    icon: Optional[str]
    header: Optional[str]
    description: Optional[str]
    chainId: int
    links: List[Link]

    # OPCIONAL, se quiser exibir o status e motivos
    status: Optional[str] = "ok"        # "ok" ou "partial"
    failed: Optional[List[str]] = []    # critérios não atendidos

    # 🔽 🔽 🔽 CAMPOS DO RETORNO DO GPT (opcionais)
    decision: Optional[str] = None      # "entrada" | "observar" | "evitar"
    confidence: Optional[float] = None  # 0–100 (pode vir com decimais)
    rationale: Optional[str] = None     # explicação curta
