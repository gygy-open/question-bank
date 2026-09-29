import pytest
from sqlalchemy import select

from app.capabilities.errors import Conflict, Invalid
from app.core.security import create_access_token
from app.models.agent import AgentRun, AgentRunStatus
from app.models.ai_config import AIModel, AIProvider
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.ai_config_service import delete_provider, validate_active_model


async def test_delete_referenced_model_preserves_agent_run(db_session):
    user = User(
        username="zz-ai-delete-test",
        full_name="AI delete test",
        hashed_password="x",
        is_active=True,
    )
    provider = AIProvider(
        name="zz-ai-delete-provider",
        interface_type="openai",
        api_key="test-key",
    )
    model = AIModel(provider=provider, name="zz-ai-delete-model")
    db_session.add_all([user, provider, model])
    await db_session.flush()

    run = AgentRun(
        user_id=user.id,
        surface="chat",
        status=AgentRunStatus.DONE,
        model_id=model.id,
        model_name=model.name,
        provider_name=provider.name,
    )
    db_session.add(run)
    await db_session.commit()

    await db_session.delete(model)
    await db_session.commit()

    persisted_run = (
        await db_session.execute(select(AgentRun).where(AgentRun.id == run.id))
    ).scalar_one()
    await db_session.refresh(persisted_run)
    assert persisted_run.model_id is None
    assert persisted_run.model_name == "zz-ai-delete-model"
    assert persisted_run.provider_name == "zz-ai-delete-provider"


async def test_delete_provider_requires_force_when_model_is_active(db_session):
    provider = AIProvider(
        name="zz-active-provider",
        interface_type="openai",
        api_key="test-key",
    )
    model = AIModel(provider=provider, name="zz-active-model")
    db_session.add_all([provider, model])
    await db_session.flush()
    setting_key = "AI_TEXT_MODEL_ID"
    setting = SystemSetting(key=setting_key, value=str(model.id))
    db_session.add(setting)
    await db_session.commit()
    provider_id = provider.id
    model_id = model.id

    with pytest.raises(Conflict, match="文本模型"):
        await delete_provider(db_session, provider_id=provider_id)

    assert await db_session.get(AIProvider, provider_id) is not None
    assert (await db_session.get(SystemSetting, setting_key)).value == str(model_id)


async def test_force_delete_provider_clears_active_config(db_session):
    provider = AIProvider(
        name="zz-force-delete-provider",
        interface_type="openai",
        api_key="test-key",
    )
    model = AIModel(provider=provider, name="zz-force-delete-model")
    db_session.add_all([provider, model])
    await db_session.flush()
    model_id = model.id
    db_session.add(SystemSetting(key="AI_VISION_MODEL_ID", value=str(model_id)))
    await db_session.commit()

    reload_embedding = await delete_provider(
        db_session, provider_id=provider.id, force=True
    )

    assert reload_embedding is False
    assert await db_session.get(AIProvider, provider.id) is None
    assert (await db_session.get(SystemSetting, "AI_VISION_MODEL_ID")).value == ""


async def test_active_config_rejects_missing_model(db_session):
    with pytest.raises(Invalid, match="不存在"):
        await validate_active_model(
            db_session, key="AI_TEXT_MODEL_ID", value="999999"
        )


async def test_provider_delete_api_requires_force_for_active_model(
    client, db_session
):
    admin = User(
        username="zz-ai-delete-admin",
        full_name="AI delete admin",
        hashed_password="x",
        is_active=True,
        is_superuser=True,
    )
    provider = AIProvider(
        name="zz-api-delete-provider",
        interface_type="openai",
        api_key="test-key",
    )
    model = AIModel(provider=provider, name="zz-api-delete-model")
    db_session.add_all([admin, provider, model])
    await db_session.flush()
    provider_id = provider.id
    model_id = model.id
    model_name = model.name
    db_session.add_all([
        SystemSetting(key="AI_TEXT_MODEL_ID", value=str(model_id)),
        AgentRun(
            user_id=admin.id,
            surface="chat",
            status=AgentRunStatus.DONE,
            model_id=model_id,
            model_name=model.name,
            provider_name=provider.name,
        ),
    ])
    await db_session.commit()
    headers = {
        "Authorization": f"Bearer {create_access_token(subject=admin.id)}"
    }

    conflict = await client.delete(
        f"/api/v1/ai-config/providers/{provider_id}", headers=headers
    )
    assert conflict.status_code == 409

    deleted = await client.delete(
        f"/api/v1/ai-config/providers/{provider_id}?force=true", headers=headers
    )
    assert deleted.status_code == 204

    db_session.expire_all()
    assert await db_session.get(AIProvider, provider_id) is None
    assert (await db_session.get(SystemSetting, "AI_TEXT_MODEL_ID")).value == ""
    persisted_run = (
        await db_session.execute(select(AgentRun).where(AgentRun.model_name == model_name))
    ).scalar_one()
    assert persisted_run.model_id is None