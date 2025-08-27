from fastapi.testclient import TestClient
from app.main import app

def test_snapshot_enriched_route_ok_sync_dup():
    client = TestClient(app)
    r = client.get("/signals/solana/snapshot_enriched/So11111111111111111111111111111111111111112")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        body = r.json()
        assert "tokenAddress" in body
        assert "score_local" in body
        assert "flags" in body
        assert "classification" in body
