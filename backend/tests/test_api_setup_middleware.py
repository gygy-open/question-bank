import app.main


async def test_api_blocked_until_configured(client, monkeypatch):
    # Simulate first-run: no database configured yet.
    monkeypatch.setattr(app.main, "is_configured", lambda: False)

    resp = await client.get("/api/v1/questions")

    assert resp.status_code == 503
    assert resp.json()["detail"] == "setup_required"


async def test_exempt_paths_bypass_setup_gate(client, monkeypatch):
    monkeypatch.setattr(app.main, "is_configured", lambda: False)

    version = await client.get("/api/v1/system/version")

    # Exempt endpoints must remain reachable before setup completes.
    assert version.status_code != 503


async def test_api_allowed_once_configured(client, monkeypatch):
    monkeypatch.setattr(app.main, "is_configured", lambda: True)

    # Middleware passes through; endpoint requires auth, so 401 (not 503).
    resp = await client.get("/api/v1/questions")

    assert resp.status_code != 503
