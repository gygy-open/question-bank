import asyncio
from sqlalchemy import text
from app.db.session import engine

async def list_tables():
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SHOW TABLES"))
            tables = result.fetchall()
            print("Tables in database:")
            for table in tables:
                print(table)
    except Exception as e:
        print(f"Error listing tables: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(list_tables())