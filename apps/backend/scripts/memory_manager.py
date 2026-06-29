"""
对话记忆管理工具 — CLI 操作 session_id 和 speaker_id 下的数据增删改查

用法:
  python scripts/memory_manager.py list --session <session_id>
  python scripts/memory_manager.py list --speaker <speaker_id>
  python scripts/memory_manager.py list --session <session_id> --speaker <speaker_id>
  python scripts/memory_manager.py list --session <session_id> --type 摘要
  python scripts/memory_manager.py get <id>
  python scripts/memory_manager.py add --session <session_id> --speaker <speaker_id> --content "内容" --type 事实 --content-type 兴趣爱好
  python scripts/memory_manager.py update <id> --content "新内容" --importance 5
  python scripts/memory_manager.py delete <id>
  python scripts/memory_manager.py stats --session <session_id>
  python scripts/memory_manager.py clear --session <session_id>

环境变量:
  CONTEXT_SQL_URL  数据库连接地址（默认 sqlite+aiosqlite:///./soulmeet.db）
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.conversation.models import init_db, ConversationMemory
from core.conversation.sql_store import SQLStore
from sqlalchemy import select, and_, func


# 从环境变量或 .env 文件读取数据库URL
def get_db_url() -> str:
    """获取数据库连接 URL"""
    url = os.environ.get("CONTEXT_SQL_URL")
    if url:
        return url
    # 尝试从 .env 文件读取
    env_file = ROOT / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("CONTEXT_SQL_URL="):
                    return line.split("=", 1)[1].strip()
    return "sqlite+aiosqlite:///./soulmeet.db"


def format_memory(r: dict, verbose: bool = False) -> str:
    """格式化单条记忆记录的显示"""
    importance_stars = "⭐" * (r.get("importance") or 0)
    status_icon = {"valid": "✅", "invalid": "⚠️"}.get(r.get("status", ""), "❓")

    lines = [
        f"  {status_icon} ID: {r['id']}  {importance_stars}",
        f"     类型: [{r['msg_type']}] {r.get('content_type') or '-'}",
        f"     内容: {r['contents'][:120]}{'...' if len(r.get('contents', '')) > 120 else ''}",
    ]
    if verbose:
        lines.extend([
            f"     Session:  {r['session_id']}",
            f"     Speaker:  {r['speaker_id']}",
            f"     Audience: {r['audiences']}",
            f"     创建时间: {r.get('create_time', '-')}",
            f"     更新时间: {r.get('updated_at', '-')}",
            f"     热度值:   {r.get('hot_values', 0)}",
            f"     最后访问: {r.get('last_accessed_at', '-')}",
            f"     元数据:   {r.get('metadata', '-')}",
        ])
    return "\n".join(lines)


async def cmd_list(sql: SQLStore, args):
    """列出记忆记录"""
    print("\n" + "=" * 70)
    print("📋 对话记忆列表")
    print("=" * 70)

    session_factory = sql._session_factory
    async with session_factory() as session:
        conditions = [ConversationMemory.status == "valid"] if not args.all else []

        if args.session:
            conditions.append(ConversationMemory.session_id == args.session)
        if args.speaker:
            conditions.append(ConversationMemory.speaker_id == args.speaker)
        if args.type:
            conditions.append(ConversationMemory.msg_type == args.type)

        stmt = (
            select(ConversationMemory)
            .where(and_(*conditions) if conditions else True)
            .order_by(ConversationMemory.create_time.desc())
            .limit(args.limit)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    if not rows:
        print("  (空) 没有找到记忆记录")
        return

    for r in reversed(rows):
        row_dict = SQLStore._row_to_dict(r)
        print(format_memory(row_dict, verbose=args.verbose))
        print(f"  {'─' * 50}")

    print(f"\n  共 {len(rows)} 条记录")


async def cmd_get(sql: SQLStore, args):
    """获取单条记忆"""
    record = await sql.get_memory_by_id(args.id)
    if not record:
        print(f"\n❌ 未找到 ID={args.id} 的记忆记录")
        return

    print("\n" + "=" * 70)
    print(f"📌 记忆详情 (ID: {args.id})")
    print("=" * 70)
    print(format_memory(record, verbose=True))


async def cmd_add(sql: SQLStore, args):
    """添加记忆记录"""
    metadata = None
    if args.subject and args.relation and args.object:
        metadata = {
            "subject": args.subject,
            "relation": args.relation,
            "object": args.object,
        }

    record_id = await sql.append_message(
        session_id=args.session,
        audiences=args.audience,
        speaker_id=args.speaker,
        content=args.content,
        msg_type=args.type,
        content_type=args.content_type,
        importance=args.importance,
        metadata=metadata,
    )

    print(f"\n✅ 记忆已添加: ID={record_id}")
    print(f"   Session:     {args.session}")
    print(f"   Speaker:     {args.speaker}")
    print(f"   类型:        [{args.type or '事实'}] {args.content_type or '-'}")
    print(f"   内容:        {args.content}")
    if metadata:
        print(f"   三元组:      {metadata}")


async def cmd_update(sql: SQLStore, args):
    """更新记忆记录"""
    kwargs = {}
    if args.content is not None:
        kwargs["contents"] = args.content
    if args.importance is not None:
        kwargs["importance"] = args.importance
    if args.content_type is not None:
        kwargs["content_type"] = args.content_type
    if args.type is not None:
        kwargs["msg_type"] = args.type

    if not kwargs:
        print("❌ 请指定要更新的字段（--content, --importance, --content-type, --type）")
        return

    result = await sql.update_memory(args.id, **kwargs)
    if result:
        print(f"\n✅ 记忆已更新: ID={args.id}")
        for k, v in kwargs.items():
            print(f"   {k} = {v}")
    else:
        print(f"\n❌ 未找到 ID={args.id} 的记忆记录")


async def cmd_delete(sql: SQLStore, args):
    """删除记忆记录（软删除）"""
    result = await sql.soft_delete_memory(args.id)
    if result:
        print(f"\n✅ 记忆已删除（软删除）: ID={args.id}")
    else:
        print(f"\n❌ 未找到 ID={args.id} 的记忆记录")


async def cmd_stats(sql: SQLStore, args):
    """统计信息"""
    print("\n" + "=" * 70)
    print("📊 记忆统计信息")
    print("=" * 70)

    session_factory = sql._session_factory
    async with session_factory() as session:
        conditions = [ConversationMemory.status == "valid"]
        if args.session:
            conditions.append(ConversationMemory.session_id == args.session)
        if args.speaker:
            conditions.append(ConversationMemory.speaker_id == args.speaker)

        # 总数
        stmt = select(func.count(ConversationMemory.id)).where(and_(*conditions))
        result = await session.execute(stmt)
        total = result.scalar() or 0

        # 按类型统计
        stmt = (
            select(ConversationMemory.msg_type, func.count(ConversationMemory.id))
            .where(and_(*conditions))
            .group_by(ConversationMemory.msg_type)
        )
        result = await session.execute(stmt)
        type_counts = result.all()

        # 按 content_type 统计
        stmt = (
            select(ConversationMemory.content_type, func.count(ConversationMemory.id))
            .where(and_(*conditions))
            .group_by(ConversationMemory.content_type)
        )
        result = await session.execute(stmt)
        content_type_counts = result.all()

    filter_desc = []
    if args.session:
        filter_desc.append(f"Session={args.session}")
    if args.speaker:
        filter_desc.append(f"Speaker={args.speaker}")
    filter_str = " | ".join(filter_desc) if filter_desc else "全部"

    print(f"\n  📌 过滤条件: {filter_str}")
    print(f"  📌 总记忆数: {total}")

    if type_counts:
        print("\n  📊 按消息类型:")
        for msg_type, count in type_counts:
            print(f"     [{msg_type}]: {count}")

    if content_type_counts:
        print("\n  📊 按内容类别:")
        for content_type, count in content_type_counts:
            print(f"     [{content_type or '未分类'}]: {count}")


async def cmd_clear(sql: SQLStore, args):
    """清空会话的所有记忆"""
    if not args.session:
        print("❌ 请指定 --session 参数")
        return

    if not args.force:
        confirm = input(f"\n⚠️  确认清空 Session={args.session} 的所有记忆？(y/N): ")
        if confirm.lower() != "y":
            print("已取消")
            return

    count = await sql.clear_session(args.session)
    print(f"\n✅ 已清空: Session={args.session}, 删除 {count} 条记忆")


async def main():
    parser = argparse.ArgumentParser(
        description="Soulmeet 对话记忆管理工具 — session_id / speaker_id 下的数据增删改查",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出某会话的所有记忆
  python scripts/memory_manager.py list --session session_001

  # 列出某用户跨会话的所有事实
  python scripts/memory_manager.py list --speaker speaker_001 --type 事实

  # 查看单条记忆详情
  python scripts/memory_manager.py get 42

  # 添加一条事实记忆（含三元组）
  python scripts/memory_manager.py add --session s1 --speaker u1 \\
      --content "用户喜欢猫" --type 事实 --content-type 兴趣爱好 \\
      --subject 用户 --relation 喜欢 --object 猫

  # 更新记忆重要程度
  python scripts/memory_manager.py update 42 --importance 5

  # 删除记忆
  python scripts/memory_manager.py delete 42

  # 查看统计信息
  python scripts/memory_manager.py stats --session session_001

  # 清空会话
  python scripts/memory_manager.py clear --session session_001 --force
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="操作命令")

    # list
    p_list = subparsers.add_parser("list", help="列出记忆记录")
    p_list.add_argument("--session", default=None, help="按 session_id 过滤")
    p_list.add_argument("--speaker", default=None, help="按 speaker_id 过滤")
    p_list.add_argument("--type", default=None, help="按 msg_type 过滤（对话/摘要/事实/工具调用）")
    p_list.add_argument("--limit", type=int, default=50, help="返回条数限制")
    p_list.add_argument("--all", action="store_true", help="包含已删除的记录")
    p_list.add_argument("-v", "--verbose", action="store_true", help="显示详细信息")

    # get
    p_get = subparsers.add_parser("get", help="查看单条记忆详情")
    p_get.add_argument("id", type=int, help="记忆 ID")

    # add
    p_add = subparsers.add_parser("add", help="添加记忆记录")
    p_add.add_argument("--session", required=True, help="会话 ID")
    p_add.add_argument("--speaker", required=True, help="说话者 ID")
    p_add.add_argument("--content", required=True, help="记忆内容")
    p_add.add_argument("--audience", default="elder", help="人群标识")
    p_add.add_argument("--type", default="事实", help="消息类型（对话/摘要/事实/工具调用）")
    p_add.add_argument("--content-type", default=None, help="内容类别（情绪波动/兴趣爱好等）")
    p_add.add_argument("--importance", type=int, default=3, help="重要程度 1-5")
    p_add.add_argument("--role", default="system", help="角色（对话类型时使用）")
    p_add.add_argument("--subject", default=None, help="三元组-主语")
    p_add.add_argument("--relation", default=None, help="三元组-关系")
    p_add.add_argument("--object", default=None, help="三元组-宾语")

    # update
    p_update = subparsers.add_parser("update", help="更新记忆记录")
    p_update.add_argument("id", type=int, help="记忆 ID")
    p_update.add_argument("--content", default=None, help="新内容")
    p_update.add_argument("--importance", type=int, default=None, help="新重要程度")
    p_update.add_argument("--content-type", default=None, help="新内容类别")
    p_update.add_argument("--type", default=None, help="新消息类型")

    # delete
    p_delete = subparsers.add_parser("delete", help="删除记忆记录（软删除）")
    p_delete.add_argument("id", type=int, help="记忆 ID")

    # stats
    p_stats = subparsers.add_parser("stats", help="统计信息")
    p_stats.add_argument("--session", default=None, help="按 session_id 过滤")
    p_stats.add_argument("--speaker", default=None, help="按 speaker_id 过滤")

    # clear
    p_clear = subparsers.add_parser("clear", help="清空会话的所有记忆")
    p_clear.add_argument("--session", required=True, help="会话 ID")
    p_clear.add_argument("--force", action="store_true", help="跳过确认")

    # 通用参数
    parser.add_argument("--db", default=None, help="数据库 URL（覆盖 CONTEXT_SQL_URL 环境变量）")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    db_url = args.db or get_db_url()
    session_factory = await init_db(db_url)
    sql = SQLStore(session_factory)

    commands = {
        "list": cmd_list,
        "get": cmd_get,
        "add": cmd_add,
        "update": cmd_update,
        "delete": cmd_delete,
        "stats": cmd_stats,
        "clear": cmd_clear,
    }

    handler = commands.get(args.command)
    if handler:
        await handler(sql, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
