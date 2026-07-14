import logging
import sys
import os
import asyncio

# Add the parent directory to sys.path to allow importing app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal, engine
from app.crud.crud_user import user as crud_user
from app.schemas.user import UserCreate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_superuser() -> None:
    async with SessionLocal() as db:
        try:
            username = "admin"
            password = "password"
            
            user = await crud_user.get_by_username(db, username=username)
            if user:
                logger.info(f"User {username} already exists")
                return

            user_in = UserCreate(
                username=username,
                password=password,
                is_superuser=True,
                is_active=True,
            )
            user = await crud_user.create(db, obj_in=user_in)
            logger.info(f"Superuser created: username={username}, password={password}")
        except Exception as e:
            logger.error(f"Error creating superuser: {e}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_superuser())
