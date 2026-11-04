"""灌入题干结构化的初始词表（元素角色 / 元素类型 / 解题方法）。

词表是数据不是模式：加一个元素类型或解题方法不需要发版、不需要迁移，改这里
重跑或者直接在管理界面加都行。

用法：
    uv run python scripts/seed_struct_vocabulary.py

重复执行安全：按 code 做 upsert，只补不删。
"""
import asyncio
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.question_structure import (  # noqa: E402
    ElementRole,
    ElementType,
    SolvingMethod,
    StructVocabularyMeta,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROLES = [
    ("object", "对象", "被研究的主语：函数式、图形、统计对象"),
    ("given", "已知", "题给的确定事实"),
    ("constraint", "限制", "对变动范围的约束"),
    ("ask", "设问", "要回答的问题"),
    ("material", "材料", "题组共享的背景材料"),
]

# 第一坐标跟着课标四**领域**走，不自造（不叫 subject，避免与题库的学科表混淆）；
# 第二坐标是作用。层级先做两档：领域节点 + 具体类型，用 parent_code 挂上去。
DOMAIN_NODES = [
    ("dom_algebra", "algebra", "form", "数与代数", 10),
    ("dom_geometry", "geometry", "form", "图形与几何", 20),
    ("dom_stat", "stat", "form", "统计与概率", 30),
    ("dom_practice", "practice", "form", "综合与实践", 40),
]

ELEMENT_TYPES = [
    ("alg_form", "algebra", "form", "式结构", "函数式 / 方程 / 不等式本身"),
    ("alg_quant", "algebra", "quant", "代数量", "坐标、系数、具体的值"),
    ("alg_qual", "algebra", "qual", "代数关系", "给关系而非给值"),
    ("alg_proc", "algebra", "proc", "参数变动", "含参、范围可变"),
    ("geo_form", "geometry", "form", "形结构", "三角形 / 四边形 / 圆本身"),
    ("geo_quant", "geometry", "quant", "几何量", "长度、角度、面积的具体值"),
    ("geo_qual", "geometry", "qual", "位置关系", "平行 / 垂直 / 相似 / 在…上"),
    ("geo_proc", "geometry", "proc", "动形", "动点、翻折、旋转"),
    ("stat_form", "stat", "form", "统计对象", "样本、图表类型"),
    ("stat_quant", "stat", "quant", "统计量", "平均数 / 方差 / 频率的值"),
    ("stat_qual", "stat", "qual", "统计关系", "相关性、分布特征"),
    ("stat_proc", "stat", "proc", "抽样过程", "抽取、频数变化"),
    ("pra_form", "practice", "form", "任务结构", "方案 / 测量 / 优化目标"),
    ("pra_quant", "practice", "quant", "实践量", "可测的量与预算"),
    ("pra_qual", "practice", "qual", "实践约束", "现实限制条件"),
    ("pra_proc", "practice", "proc", "实施过程", "操作步骤可变"),
]

# weight > 1 表示认知负荷突增的步骤。思维量 = 步骤权重之和。
SOLVING_METHODS = [
    ("def_coef", "待定系数法", None, 1.0),
    ("vertex", "配方 / 顶点式", None, 1.0),
    ("deriv", "求导判断单调与极值", None, 1.0),
    ("pythagoras", "勾股定理列方程", None, 1.0),
    ("ratio_check", "边比 / 对应关系验证", None, 1.0),
    ("substitute", "代入消元", None, 1.0),
    ("classify", "分类讨论", None, 1.5),
    ("exhaust", "穷举所有情形", None, 1.5),
    ("counterexample", "举反例否证", None, 1.5),
    ("auxiliary_line", "构造辅助线", None, 1.5),
    ("transform", "转化（几何转代数等）", None, 1.4),
    ("exclude_degen", "排除退化情形", None, 1.3),
    ("judge", "判定命题真假", None, 1.2),
]

META = [
    ("vocabulary", "2026-11-04"),
    ("scope", "math"),
    ("note", "初始词表，学科老师可直接增改；code 一经使用不要改名"),
]


async def _upsert(session, model, code, payload):
    existing = await session.get(model, code)
    if existing is None:
        session.add(model(code=code, **payload))
        return True
    for key, value in payload.items():
        setattr(existing, key, value)
    return False


async def main() -> None:
    async with SessionLocal() as session:
        added = changed = 0
        for code, name, note in ROLES:
            if await _upsert(session, ElementRole, code, {"name": name, "note": note}):
                added += 1
            else:
                changed += 1
        for code, domain, action, name, sort_order in DOMAIN_NODES:
            if await _upsert(session, ElementType, code, {
                "domain": domain, "action": action, "name": name,
                "sort_order": sort_order, "status": "active", "parent_code": None,
            }):
                added += 1
            else:
                changed += 1
        for code, domain, action, name, note in ELEMENT_TYPES:
            parent = "dom_" + domain
            if await _upsert(session, ElementType, code, {
                "domain": domain, "action": action, "name": name, "note": note,
                "parent_code": parent, "sort_order": 0, "status": "active",
            }):
                added += 1
            else:
                changed += 1
        for code, name, parent, weight in SOLVING_METHODS:
            if await _upsert(session, SolvingMethod, code, {
                "name": name, "parent_code": parent, "weight": weight,
            }):
                added += 1
            else:
                changed += 1
        for key, value in META:
            if await _upsert(session, StructVocabularyMeta, key, {"value": value}):
                added += 1
        await session.commit()
        logger.info("词表初始化完成：新增 %d，更新 %d", added, changed)


if __name__ == "__main__":
    asyncio.run(main())
