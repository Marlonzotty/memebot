import requests

def get_token_profiles():
    url = "https://api.dexscreener.com/token-profiles/latest/v1"
    headers = {"Accept": "*/*", "User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            print("Erro HTTP:", response.status_code)
            return []

        tokens = response.json()

        result = []
        for token in tokens:
            result.append({
                "tokenAddress": token.get("tokenAddress"),
                "url": token.get("url"),
                "icon": token.get("icon"),
                "header": token.get("header"),
                "description": token.get("description"),
                "chainId": token.get("chainId"),
                "links": token.get("links", [])
            })

        return result

    except Exception as e:
        print("Erro ao buscar tokens:", e)
        return []
