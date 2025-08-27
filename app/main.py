from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import signals
from app.routers.signals import router as signals_router
from app.routers import links
from app.routers import tokens

app = FastAPI(title="MemeBot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # ambiente local
        "https://crypto-green-two.vercel.app",  # produção
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(signals_router)
app.include_router(links.router)
app.include_router(tokens.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
