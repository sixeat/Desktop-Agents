import argparse
import sys
from pathlib import Path

from core.lora_dataset import build_lora_dataset, write_lora_jsonl
from tools.wechat.parsers import load_export_dir, load_messages

PRIVACY_NOTICE = """
隐私提示：LoRA 训练集会保存成对的原始对话片段，可能包含个人聊天内容。
本工具只在本地处理你显式提供的导出/已解密数据库文件，不会上传数据。
工具会过滤疑似密码、验证码、token、API Key 和长密钥，但不能保证 100% 清除敏感信息；训练或分享前请人工检查 train.jsonl。
""".strip()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从本地聊天记录导出 LoRA 训练 JSONL")
    parser.add_argument("--wxid", required=True, help="要学习说话风格的目标联系人 wxid/标识")
    parser.add_argument("--db", action="append", default=[], help="已解密 SQLite/可显式给 key 的 MSG 数据库路径，可重复")
    parser.add_argument("--export-dir", help="wechat-dump-rs 等工具的本地导出目录")
    parser.add_argument("--sqlcipher-key", help="显式提供的 SQLCipher key；本工具不会自动提取 key")
    parser.add_argument("--self-wxid", help="当前登录用户 wxid，用于辅助判断消息方向")
    parser.add_argument("--out", default="train.jsonl", help="输出 JSONL 路径，默认 train.jsonl")
    parser.add_argument("--limit", type=int, default=5000, help="最多读取的消息数量")
    parser.add_argument("--include-groups", action="store_true", help="尽量包含群聊中可识别为目标发出的文本")
    parser.add_argument("--min-user-chars", type=int, default=2, help="用户侧消息最短字符数")
    parser.add_argument("--min-assistant-chars", type=int, default=2, help="目标回复最短字符数")
    parser.add_argument("--max-examples", type=int, help="最多导出的训练样本数")
    parser.add_argument("--dry-run", action="store_true", help="只打印统计，不写入 JSONL")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有输出 JSONL")
    parser.add_argument("--quiet", action="store_true", help="不打印隐私提示")
    parser.add_argument("--verbose", action="store_true", help="打印更多诊断信息")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    if not args.db and not args.export_dir:
        raise ValueError("请至少提供 --db 或 --export-dir")
    if args.sqlcipher_key and not args.db:
        raise ValueError("--sqlcipher-key 需要配合 --db 使用")

    if not args.quiet:
        print(PRIVACY_NOTICE)
        print()

    messages = []
    warnings: list[str] = []
    if args.db:
        db_messages, report = load_messages(
            [Path(path) for path in args.db],
            wxid=args.wxid,
            self_wxid=args.self_wxid,
            sqlcipher_key=args.sqlcipher_key,
            limit=args.limit,
            include_groups=args.include_groups,
            verbose=args.verbose,
        )
        messages.extend(db_messages)
        warnings.extend(report.warnings)

    if args.export_dir:
        export_messages, report = load_export_dir(
            Path(args.export_dir),
            wxid=args.wxid,
            self_wxid=args.self_wxid,
            limit=args.limit,
            include_groups=args.include_groups,
            verbose=args.verbose,
        )
        messages.extend(export_messages)
        warnings.extend(report.warnings)

    messages.sort(key=lambda message: message.timestamp or 0)
    if args.limit > 0:
        messages = messages[-args.limit:]

    result = build_lora_dataset(
        messages,
        min_user_chars=args.min_user_chars,
        min_assistant_chars=args.min_assistant_chars,
        max_examples=args.max_examples,
    )
    output_path = Path(args.out)
    print_summary(result.stats, output_path, warnings)

    if args.dry_run:
        print("dry-run 模式：未写入 LoRA 训练 JSONL。")
        return 0
    if not result.examples:
        print("未生成可训练样本，未写入文件。", file=sys.stderr)
        return 2

    write_lora_jsonl(result.examples, output_path, overwrite=args.overwrite)
    print(f"已写入 LoRA 训练集：{output_path}")
    return 0


def print_summary(stats, output_path: Path, warnings: list[str]) -> None:
    print("LoRA 数据集摘要：")
    print(f"- 读取文本消息：{stats.records_seen}")
    print(f"- 生成训练样本：{stats.examples}")
    print(f"- 跳过空/非文本：{stats.skipped_empty}")
    print(f"- 跳过疑似敏感内容：{stats.skipped_sensitive}")
    print(f"- 跳过过短消息：{stats.skipped_short}")
    print(f"- 跳过未配对消息：{stats.skipped_unpaired}")
    print(f"- 输出路径：{output_path}")
    for warning in warnings:
        print(f"警告：{warning}")


if __name__ == "__main__":
    raise SystemExit(main())
