from fastapi import APIRouter
from app.api.v1.endpoints import subjects, knowledge_points, tags, tag_categories, questions, upload, login, users, system_settings, papers, ai_config, chat, tools, activity_logs, import_tasks, prompts, setup

api_router = APIRouter()
api_router.include_router(setup.router, prefix="/setup", tags=["setup"])
api_router.include_router(login.router, tags=["login"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(subjects.router, prefix="/subjects", tags=["subjects"])
api_router.include_router(knowledge_points.router, prefix="/knowledge-points", tags=["knowledge-points"])
api_router.include_router(tags.router, prefix="/tags", tags=["tags"])
api_router.include_router(tag_categories.router, prefix="/tag-categories", tags=["tag-categories"])
api_router.include_router(questions.router, prefix="/questions", tags=["questions"])
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(import_tasks.router, prefix="/imports", tags=["imports"])
api_router.include_router(system_settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(papers.router, prefix="/papers", tags=["papers"])
api_router.include_router(ai_config.router, prefix="/ai-config", tags=["ai-config"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(prompts.router, prefix="/chat/prompts", tags=["prompts"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(activity_logs.router, prefix="/activity-logs", tags=["activity-logs"])


