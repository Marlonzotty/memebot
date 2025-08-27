import os
import requests
from typing import List, Optional
from app.models.signal_model import Signal
from app.services.grok_service import GrokService

class XService:
    def __init__(self):
        self.api_key = os.getenv("afbS86WFdhVlnorlTTzHofCVeCTjp4Irb022Ln6hcS6tuHeyxc")  # Chave da API do X ou twitterapi.io
        self.base_url = "https://api.twitterapi.io/v1"  # Substitua por API real
        self.grok = GrokService()

    async def fetch_kol_tweets(self, kols: List[str], query: str) -> List[dict]:
        """Busca tweets de KOLs com base em uma query."""
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {"q": f"from:{','.join(kols)} {query}", "count": 10}
            response = requests.get(f"{self.base_url}/search/tweets", headers=headers, params=params)
            response.raise_for_status()
            return response.json().get("statuses", [])
        except Exception as e:
            print(f"[XService] Erro ao buscar tweets: {e}")
            return []

    async def analyze_tweet_sentiment(self, tweet_text: str) -> dict:
        """Analisa o sentiment de um tweet usando Grok."""
        prompt = f"""
        Analise o sentiment do seguinte tweet sobre um token de criptomoeda:
        Tweet: "{tweet_text}"
        Retorne um JSON com:
        - sentiment_score: float entre -1 (negativo) e 1 (positivo)
        - action: string ("buy", "watchlist", "none") baseada no score (>0.7 = buy, >0.3 = watchlist, else none)
        """
        try:
            response = await self.grok.analyze(prompt)
            return response  # Assume que Grok retorna {"sentiment_score": float, "action": str}
        except Exception as e:
            print(f"[XService] Erro ao analisar tweet: {e}")
            return {"sentiment_score": 0.0, "action": "none"}

    async def monitor_kol_tweets(self, token_address: str, kols: List[str]) -> Optional[Signal]:
        """Monitora tweets de KOLs para um token e atualiza o Signal."""
        tweets = await self.fetch_kol_tweets(kols, token_address)
        if not tweets:
            return None

        tweet_texts = [tweet["text"] for tweet in tweets]
        sentiments = [await self.analyze_tweet_sentiment(text) for text in tweet_texts]
        avg_score = sum(s["sentiment_score"] for s in sentiments) / len(sentiments) if sentiments else 0.0
        action = max(sentiments, key=lambda s: s["sentiment_score"], default={"action": "none"})["action"]

        return Signal(
            tokenAddress=token_address,
            chainId=101,  # Ex.: Solana
            kol_sentiment_score=avg_score,
            kol_action=action,
            kol_tweets=tweet_texts,
            links=[],
            failed=[],
            flags=[],
        )