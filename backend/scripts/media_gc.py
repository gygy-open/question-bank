"""媒体回收。默认只预演并输出报告,加 --apply 才删除。

    uv run python scripts/media_gc.py                    # 预演
    uv run python scripts/media_gc.py --apply            # 删除
    uv run python scripts/media_gc.py --grace-days 30    # 调整宽限期(默认 7 天)
"""
import argparse
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal, engine  # noqa: E402
from app.services.media_gc import DEFAULT_GRACE_DAYS, collect_garbage  # noqa: E402


async def main(apply: bool, grace_days: int) -> None:
    async with SessionLocal() as db:
        report = await collect_garbage(db, apply=apply, grace_days=grace_days)
    await engine.dispose()
    print("\n".join(report.lines()))
    print("已执行。" if apply else "预演完成，未做任何修改；确认后加 --apply 执行。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="实际删除(默认只预演)")
    parser.add_argument("--grace-days", type=int, default=DEFAULT_GRACE_DAYS, help="只回收早于该天数的对象/软删除资产")
    args = parser.parse_args()
    asyncio.run(main(args.apply, max(args.grace_days, 1)))
