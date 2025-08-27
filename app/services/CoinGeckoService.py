import requests
import time

class CoinGeckoService:
    COINGECKO_API_URL = "https://api.coingecko.com/api/v3/coins"

    @staticmethod
    def get_token_data_from_coingecko(token_address: str):
        if not token_address or not isinstance(token_address, str):
            print(f"Erro: token_address inválido: {token_address}")
            return {}

        try:
            response = requests.get(f"{CoinGeckoService.COINGECKO_API_URL}/{token_address}")
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 429:
                print("Erro HTTP 429: Limite de requisições atingido. Aguardando 1 segundo...")
                time.sleep(1)
                return {}
            
            if response.status_code != 200:
                print(f"Erro HTTP {response.status_code}: {response.text}")
                return {}

            token_data = response.json()
            data = {
                "priceUSD": token_data.get("market_data", {}).get("current_price", {}).get("usd", None),
                "mcapUSD": token_data.get("market_data", {}).get("market_cap", {}).get("usd", None),
                "volumeUSD_24h": token_data.get("market_data", {}).get("total_volume", {}).get("usd", None),
                "icon": token_data.get("image", {}).get("large", None),
                "url": f"https://www.coingecko.com/en/coins/{token_address}",
                "name": token_data.get("name"),
                "symbol": token_data.get("symbol"),
            }
            time.sleep(0.2)
            return data

        except Exception as e:
            print(f"Erro ao buscar dados da CoinGecko: {e}")
            import traceback
            traceback.print_exc()
            return {}