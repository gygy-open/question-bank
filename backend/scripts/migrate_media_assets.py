"""存量媒体迁移。默认只预演并输出报告,加 --apply 才写入。

    uv run python scripts/migrate_media_assets.py              # 预演
    uv run python scripts/migrate_media_assets.py --apply      # 执行迁移
    uv run python scripts/migrate_media_assets.py --purge-legacy          # 预演清理旧目录
    uv run python scripts/migrate_media_assets.py --purge-legacy --apply  # 删除已迁移的旧文件

执行前请先备份数据库与数据目录。清理旧目录只删除内容已确认保存在对象存储的文件。
"""
import argparse
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal, engine  # noqa: E402
from app.services.media_migration import migrate_media, purge_legacy_files  # noqa: E402


async def main(apply: bool, purge: bool) -> None:
    async with SessionLocal() as db:
        if purge:
            report = await purge_legacy_files(db, apply=apply)
        else:
            report = await migrate_media(db, apply=apply)
    await engine.dispose()
    print("\n".join(report.lines()))
    print("已执行。" if apply else "预演完成，未做任何修改；确认后加 --apply 执行。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="实际写入/删除(默认只预演)")
    parser.add_argument("--purge-legacy", action="store_true", help="清理已迁移的旧 static/media 与 uploads 文件")
    args = parser.parse_args()
    asyncio.run(main(args.apply, args.purge_legacy))
