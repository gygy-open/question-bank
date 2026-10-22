"""Personal AI providers: ownership, key secrecy, model resolution order, global guards."""
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.core.secrets import decrypt_secret, encrypt_secret, is_encrypted
from app.core.security import create_access_token
from app.models.ai_config import AIModel, AIProvider, UserAIPreference
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.ai_config_service import guess_capabilities
from app.services.ai_resolver import resolve_model

API = "/api/v1/ai-config"


async def _user(db, name: str, *, admin: bool = False) -> User:
    user = User(username=name, full_name=name, hashed_password="x", is_active=True, is_superuser=admin)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _provider_body(name: str, *models: dict) -> dict:
    return {
        "name": name,
        "interface_type": "openai",
        "base_url": "https://example.test/v1",
        "api_key": "sk-secret-123",
        "models": list(models),
    }


async def _global_model(db, *, name="g-chat", vision=False, embedding=False) -> AIModel:
    provider = AIProvider(name=f"global-{name}", interface_type="openai", api_key=encrypt_secret("sk-global"))
    model = AIModel(provider=provider, name=name, is_vision_capable=vision, is_embedding_model=embedding)
    db.add_all([provider, model])
    await db.commit()
    return model


def test_secret_roundtrip_and_legacy_plaintext():
    token = encrypt_secret("sk-abc")
    assert is_encrypted(token) and "sk-abc" not in token
    assert decrypt_secret(token) == "sk-abc"
    assert decrypt_secret("sk-legacy") == "sk-legacy"
    assert encrypt_secret(token) == token


def test_guess_capabilities():
    assert guess_capabilities("text-embedding-3-small")["is_embedding_model"]
    assert guess_capabilities("gpt-4o")["is_vision_capable"]
    assert guess_capabilities("qwen-vl-max")["is_vision_capable"]
    assert guess_capabilities("deepseek-chat") == {"is_vision_capable": False, "is_embedding_model": False}


async def test_personal_provider_is_private_and_key_never_returned(client, db_session):
    alice = await _user(db_session, "alice")
    bob = await _user(db_session, "bob")
    admin = await _user(db_session, "admin", admin=True)

    resp = await client.post(
        f"{API}/me/providers",
        json=_provider_body("Mine", {"name": "my-chat"}),
        headers=_auth(alice),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_personal"] and body["owner_id"] == alice.id and body["api_key_set"]
    assert "api_key" not in body
    provider_id = body["id"]
    model_id = body["models"][0]["id"]

    stored = await db_session.get(AIProvider, provider_id)
    assert is_encrypted(stored.api_key) and decrypt_secret(stored.api_key) == "sk-secret-123"

    # Same name is fine for another owner.
    resp = await client.post(f"{API}/me/providers", json=_provider_body("Mine"), headers=_auth(bob))
    assert resp.status_code == 200
    # Duplicate under the same owner is rejected.
    resp = await client.post(f"{API}/me/providers", json=_provider_body("Mine"), headers=_auth(alice))
    assert resp.status_code == 409

    names_for_bob = [p["name"] for p in (await client.get(f"{API}/providers", headers=_auth(bob))).json()]
    assert names_for_bob.count("Mine") == 1  # only his own

    # Bob cannot touch Alice's provider/model.
    assert (await client.put(f"{API}/me/providers/{provider_id}", json={"name": "x"}, headers=_auth(bob))).status_code == 404
    assert (await client.delete(f"{API}/me/models/{model_id}", headers=_auth(bob))).status_code == 404
    assert (await client.put(f"{API}/me/preferences", json={"text_model_id": model_id}, headers=_auth(bob))).status_code == 400
    # Global endpoints don't operate on personal providers.
    assert (await client.put(f"{API}/providers/{provider_id}", json={"name": "x"}, headers=_auth(admin))).status_code == 404

    # Admin can review (without keys) and delete.
    listed = (await client.get(f"{API}/providers?include_personal=true", headers=_auth(admin))).json()
    mine = next(p for p in listed if p["id"] == provider_id)
    assert mine["owner_name"] == "alice" and "api_key" not in mine
    assert (await client.get(f"{API}/providers?include_personal=true", headers=_auth(alice))).status_code == 403
    assert (await client.delete(f"{API}/providers/{provider_id}", headers=_auth(admin))).status_code == 204


async def test_update_keeps_key_when_blank(client, db_session):
    alice = await _user(db_session, "alice")
    created = (await client.post(f"{API}/me/providers", json=_provider_body("P"), headers=_auth(alice))).json()
    resp = await client.put(
        f"{API}/me/providers/{created['id']}",
        json={"name": "P2", "api_key": "", "is_active": False},
        headers=_auth(alice),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "P2" and resp.json()["is_active"] is False
    stored = await db_session.get(AIProvider, created["id"])
    await db_session.refresh(stored)
    assert decrypt_secret(stored.api_key) == "sk-secret-123"


async def test_resolution_order_explicit_personal_global(client, db_session):
    alice = await _user(db_session, "alice")
    alice_id = alice.id
    headers = _auth(alice)
    global_model = await _global_model(db_session)
    global_id = global_model.id
    db_session.add(SystemSetting(key="AI_TEXT_MODEL_ID", value=str(global_id)))
    await db_session.commit()

    resolved = await resolve_model(db_session, user_id=alice_id, purpose="text")
    assert resolved.model.id == global_id and resolved.source == "global"
    assert resolved.config["API_KEY"] == "sk-global"

    created = (await client.post(
        f"{API}/me/providers", json=_provider_body("Mine", {"name": "my-chat"}), headers=headers
    )).json()
    my_model_id = created["models"][0]["id"]
    resp = await client.put(f"{API}/me/preferences", json={"text_model_id": my_model_id}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["effective_text"] == {"model_id": my_model_id, "source": "personal", "error": None}

    resolved = await resolve_model(db_session, user_id=alice_id, purpose="text")
    assert resolved.model.id == my_model_id and resolved.config["API_KEY"] == "sk-secret-123"

    # Disabling the personal provider falls back to global.
    await client.put(f"{API}/me/providers/{created['id']}", json={"is_active": False}, headers=headers)
    db_session.expire_all()
    resolved = await resolve_model(db_session, user_id=alice_id, purpose="text")
    assert resolved.model.id == global_id

    # Deleting the personal model clears the preference.
    await client.delete(f"{API}/me/models/{my_model_id}", headers=headers)
    db_session.expire_all()
    pref = await db_session.get(UserAIPreference, alice_id)
    assert pref.text_model_id is None


async def test_embedding_and_vision_capability_enforced(client, db_session):
    alice = await _user(db_session, "alice")
    created = (await client.post(
        f"{API}/me/providers",
        json=_provider_body("Mine", {"name": "emb", "is_embedding_model": True}, {"name": "txt"}),
        headers=_auth(alice),
    )).json()
    ids = {m["name"]: m["id"] for m in created["models"]}
    assert (await client.put(f"{API}/me/preferences", json={"text_model_id": ids["emb"]}, headers=_auth(alice))).status_code == 400
    assert (await client.put(f"{API}/me/preferences", json={"vision_model_id": ids["txt"]}, headers=_auth(alice))).status_code == 400

    # Model flags can be edited in place.
    resp = await client.put(f"{API}/me/models/{ids['txt']}", json={"is_vision_capable": True}, headers=_auth(alice))
    assert resp.status_code == 200 and resp.json()["is_vision_capable"] is True
    assert (await client.put(f"{API}/me/preferences", json={"vision_model_id": ids["txt"]}, headers=_auth(alice))).status_code == 200


async def test_admin_cannot_activate_personal_or_wrong_capability_model(client, db_session):
    admin = await _user(db_session, "admin", admin=True)
    alice = await _user(db_session, "alice")
    personal = (await client.post(
        f"{API}/me/providers", json=_provider_body("Mine", {"name": "my-chat"}), headers=_auth(alice)
    )).json()["models"][0]["id"]
    embedding = await _global_model(db_session, name="emb", embedding=True)
    text_only = await _global_model(db_session, name="txt")

    for body in (
        {"text_model_id": personal},
        {"text_model_id": embedding.id},
        {"vision_model_id": text_only.id},
    ):
        resp = await client.post(f"{API}/active-config", json=body, headers=_auth(admin))
        assert resp.status_code == 400, body


async def test_chat_rejects_other_users_model(client, db_session):
    alice = await _user(db_session, "alice")
    bob = await _user(db_session, "bob")
    model_id = (await client.post(
        f"{API}/me/providers", json=_provider_body("Mine", {"name": "my-chat"}), headers=_auth(alice)
    )).json()["models"][0]["id"]
    session = (await client.post("/api/v1/chat/sessions", json={"title": "t"}, headers=_auth(bob))).json()
    resp = await client.post(
        f"/api/v1/chat/sessions/{session['id']}/messages",
        json={"model_id": model_id, "message": {"role": "user", "content": "hi"}},
        headers=_auth(bob),
    )
    assert resp.status_code == 400


async def test_discover_models_uses_saved_key_and_reports_failure(client, db_session):
    alice = await _user(db_session, "alice")
    bob = await _user(db_session, "bob")
    provider_id = (await client.post(f"{API}/me/providers", json=_provider_body("Mine"), headers=_auth(alice))).json()["id"]

    fake = AsyncMock(return_value=["gpt-4o", "text-embedding-3-small"])
    with patch("app.services.ai_config_service._list_remote_models", fake):
        resp = await client.post(f"{API}/discover-models", json={"provider_id": provider_id}, headers=_auth(alice))
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] and {m["name"] for m in data["models"]} == {"gpt-4o", "text-embedding-3-small"}
    assert fake.await_args.args[2] == "sk-secret-123"

    # Someone else can't borrow Alice's stored key.
    resp = await client.post(f"{API}/discover-models", json={"provider_id": provider_id}, headers=_auth(bob))
    assert resp.status_code == 404

    class Unauthorized(Exception):
        status_code = 401

    with patch("app.services.ai_config_service._list_remote_models", AsyncMock(side_effect=Unauthorized())):
        resp = await client.post(
            f"{API}/discover-models",
            json={"interface_type": "openai", "api_key": "bad"},
            headers=_auth(alice),
        )
    assert resp.json() == {"ok": False, "message": "API Key 无效或没有权限", "models": []}


async def test_deleting_user_removes_personal_providers(db_session):
    alice = await _user(db_session, "alice")
    provider = AIProvider(name="Mine", interface_type="openai", api_key="k", owner_id=alice.id)
    db_session.add_all([provider, AIModel(provider=provider, name="m")])
    await db_session.commit()

    await db_session.delete(alice)
    await db_session.commit()
    assert (await db_session.execute(select(AIProvider))).scalars().all() == []
    assert (await db_session.execute(select(AIModel))).scalars().all() == []
