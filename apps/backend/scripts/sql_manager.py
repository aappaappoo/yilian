"""
数据库查询工具 — 查看对话记忆（摘要和事件）
用法: python scripts/sql_manager.py [命令] [参数]

示例:
  python scripts/sql_manager.py summaries                     # 查看所有摘要
  python scripts/sql_manager.py summaries --session session_001
  python scripts/sql_manager.py events                        # 查看所有事件
  python scripts/sql_manager.py events --speaker speaker_001  # 某用户的所有事件
  python scripts/sql_manager.py all --session session_001     # 某会话全部记录
"""

import asyncio
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.conversation.models import init_db, ConversationMemory
from core.conversation.sql_store import SQLStore
from sqlalchemy import select, and_

# ── 数据库路径（和你 main.py 中配置一致）──
DB_URL = "sqlite+aiosqlite:///./soulmeet.db"


async def query_summaries(sql: SQLStore, session_id: str = None, speaker_id: str = None, audiences: str = None):
    """查询摘要"""
    print("\n" + "=" * 70)
    print("📝 对话摘要记录")
    print("=" * 70)

    if audiences:
        rows = await sql.get_summaries(audiences, limit=50)
    else:
        async with sql._session_factory() as session:
            conditions = [
                ConversationMemory.msg_type == "摘要",
                ConversationMemory.status == "valid",
            ]
            if session_id:
                conditions.append(ConversationMemory.session_id == session_id)
            if speaker_id:
                conditions.append(ConversationMemory.speaker_id == speaker_id)

            stmt = (
                select(ConversationMemory)
                .where(and_(*conditions))
                .order_by(ConversationMemory.create_time.desc())
                .limit(100)
            )
            result = await session.execute(stmt)
            db_rows = result.scalars().all()
            rows = [SQLStore._row_to_dict(r) for r in db_rows]

    if not rows:
        print("  (空) 没有找到摘要记录")
        return

    for r in rows:
        print(f"\n  ID: {r.get('id')}")
        print(f"  Session:  {r.get('session_id')}")
        print(f"  Speaker:  {r.get('speaker_id')}")
        print(f"  Audience: {r.get('audiences', 'N/A')}")
        print(f"  重要度:   {'⭐' * (r.get('importance') or 0)}")
        print(f"  热度值:   {r.get('hot_values', 0)}")
        print(f"  创建时间: {r.get('create_time')}")
        print(f"  摘要内容: {r.get('contents', '')[:200]}")
        print(f"  {'─' * 50}")

    print(f"\n  共 {len(rows)} 条摘要")


async def query_events(sql: SQLStore, session_id: str = None, speaker_id: str = None, audiences: str = None, user_id: str = None):
    """查询事件"""
    print("\n" + "=" * 70)
    print("⭐ 重要事件记录")
    print("=" * 70)

    if audiences:
        rows = await sql.get_events(
            audiences,
            user_id=user_id or "",
            speaker_id=speaker_id or "",
            limit=100,
        )
    elif speaker_id:
        async with sql._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(
                    and_(
                        ConversationMemory.speaker_id == speaker_id,
                        ConversationMemory.msg_type == "事实",
                        ConversationMemory.status == "valid",
                    )
                )
                .order_by(ConversationMemory.importance.desc())
                .limit(100)
            )
            result = await session.execute(stmt)
            db_rows = result.scalars().all()
            rows = [SQLStore._row_to_dict(r) for r in db_rows]
    elif session_id:
        async with sql._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(
                    and_(
                        ConversationMemory.session_id == session_id,
                        ConversationMemory.msg_type == "事实",
                        ConversationMemory.status == "valid",
                    )
                )
                .order_by(ConversationMemory.importance.desc())
                .limit(100)
            )
            result = await session.execute(stmt)
            db_rows = result.scalars().all()
            rows = [SQLStore._row_to_dict(r) for r in db_rows]
    else:
        async with sql._session_factory() as session:
            stmt = (
                select(ConversationMemory)
                .where(
                    and_(
                        ConversationMemory.msg_type == "事实",
                        ConversationMemory.status == "valid",
                    )
                )
                .order_by(ConversationMemory.importance.desc())
                .limit(100)
            )
            result = await session.execute(stmt)
            db_rows = result.scalars().all()
            rows = [SQLStore._row_to_dict(r) for r in db_rows]

    if not rows:
        print("  (空) 没有找到事件记录")
        return

    for r in rows:
        stars = "⭐" * (r.get("importance") or 0)
        print(f"  {stars} [{r.get('content_type', '未分类')}] {r.get('contents', '')}")
        print(f"       Session={r.get('session_id')}, Speaker={r.get('speaker_id')}, 创建={r.get('create_time')}")

    print(f"\n  共 {len(rows)} 条事件")


async def main():
    parser = argparse.ArgumentParser(description="Soulmeet 数据库查询工具")
    parser.add_argument(
        "command",
        choices=["summaries", "events", "all"],
        help="查询类型: summaries(摘要) / events(事件) / all(全部)",
    )
    parser.add_argument("--session", default=None, help="按 session_id 过滤")
    parser.add_argument("--speaker", default=None, help="按 speaker_id 过滤")
    parser.add_argument("--audiences", default=None, help="按 audiences 过滤（摘要查询推荐使用）")
    parser.add_argument("--user-id", default=None, dest="user_id", help="按 user_id 过滤（events 查询时与 audiences 配合使用）")
    parser.add_argument("--db", default=DB_URL, help="数据库URL")
    args = parser.parse_args()

    session_factory = await init_db(args.db)
    sql = SQLStore(session_factory)

    if args.command in ("summaries", "all"):
        await query_summaries(sql, args.session, args.speaker, args.audiences)
    if args.command in ("events", "all"):
        await query_events(sql, args.session, args.speaker, args.audiences, args.user_id)


if __name__ == "__main__":
    asyncio.run(main())