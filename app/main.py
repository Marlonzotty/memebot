# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import signals

app = FastAPI(title="MemeBot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",                 # dev local
        "https://crypto-green-two.vercel.app",   # seu front em produção
    ],
    allow_origin_regex=r"^https://.*\.vercel\.app$",  # previews da Vercel
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(signals.router)
