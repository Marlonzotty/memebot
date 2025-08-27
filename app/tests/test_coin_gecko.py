import sys
import os

# Adiciona a raiz do projeto ao caminho do Python
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.services.CoinGeckoService import CoinGeckoService
