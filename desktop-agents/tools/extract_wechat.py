import argparse
import json
import os
import re
import sys
from pathlib import Path

from config import PERSONAS_DIR
from tools.wechat.analyzer import build_personality, summarize_messages
from tools.wechat.parsers import load_export_dir, load_messages

PRIVACY_NOTICE = """
隐私提示：本工具只在本地处理你显式提供的微信导出/已解密数据库文件，不会上传数据。
本工具不会读取微信进程内存、不会提取密钥、不会绕过加密；如需处理加密库，请使用手动导出/解密结果，或显式提供你已拥有的 SQLCipher key。
输出的人格 JSON 只包含统计后的风格、话题和描述，不保存原始聊天记录。
""".strip()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从本地微信导出聊天记录生成桌面 Agent 人格 JSON")
    parser.add_argument("--guide", action="store_true", help="显示项目内教学流程，不读取聊天记录")
    parser.add_argument("--wizard", action="store_true", help="启动交互式安全向导")
    parser.add_argument("--wxid", help="要分析的联系人 wxid/标识")
    parser.add_argument("--db", action="append", default=[], help="已解密 SQLite/可显式给 key 的 MSG 数据库路径，可重复")
    parser.add_argument("--export-dir", help="wechat-dump-rs 等工具的本地导出目录")
    parser.add_argument("--sqlcipher-key", help="显式提供的 SQLCipher key；本工具不会自动提取 key")
    parser.add_argument("--out", help="输出人格 JSON 路径，默认 models/personas/wechat_<wxid>.json")
    parser.add_argument("--name", help="生成的人格显示名")
    parser.add_argument("--self-wxid", help="当前登录用户 wxid，用于辅助判断消息方向")
    parser.add_argument("--limit", type=int, default=5000, help="最多分析的消息数量")
    parser.add_argument("--min-messages", type=int, default=20, help="低于该消息数时给出提醒")
    parser.add_argument("--include-groups", action="store_true", help="尽量包含群聊中可识别为目标发出的文本")
    parser.add_argument("--dry-run", action="store_true", help="只打印分析摘要，不写入 JSON")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有输出 JSON")
    parser.add_argument("--quiet", action="store_true", help="不打印隐私提示")
    parser.add_argument("--verbose", action="store_true", help="打印更多诊断信息")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    if args.guide:
        print_guide()
        return 0
    if args.wizard:
        return run_wizard(args)
    if not args.wxid:
        raise ValueError("请提供 --wxid，或使用 --guide/--wizard 查看教学流程")
    if not args.db and not args.export_dir:
        raise ValueError("请至少提供 --db 或 --export-dir")
    if args.sqlcipher_key and not args.db:
        raise ValueError("--sqlcipher-key 需要配合 --db 使用")

    if not args.quiet:
        print(PRIVACY_NOTICE)
        print()

    db_paths = [Path(path) for path in args.db]
    messages = []
    warnings: list[str] = []

    if db_paths:
        db_messages, report = load_messages(
            db_paths,
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

    if not messages:
        print("未提取到可分析的文本消息。", file=sys.stderr)
        for warning in warnings:
            print(f"警告：{warning}", file=sys.stderr)
        return 2

    target_messages = [message for message in messages if message.is_from_target]
    if len(target_messages) < args.min_messages:
        warnings.append(f"目标发送的文本消息较少（{len(target_messages)} 条），生成的人格可能不稳定。")

    persona = build_personality(messages, wxid=args.wxid, display_name=args.name)
    summary = summarize_messages(messages)
    print("分析摘要：")
    print(f"- 总文本消息：{summary['total_messages']}")
    print(f"- 目标发送消息：{summary['target_messages']}")
    print(f"- 生成人格：{persona['name']}")
    print(f"- 语气：{persona['tone']}")
    print(f"- 话题：{'、'.join(persona['topics'])}")
    print(f"- 风格：{'、'.join(persona['style'])}")
    for warning in warnings:
        print(f"警告：{warning}")

    output_path = Path(args.out) if args.out else default_output_path(args.wxid)
    if args.dry_run:
        print("dry-run 模式：未写入人格 JSON。")
        return 0

    if output_path.exists() and not args.overwrite:
        raise FileExistsError(f"输出文件已存在：{output_path}。如需覆盖请加 --overwrite。")
    write_persona_json(persona, output_path)
    print(f"已写入人格配置：{output_path}")
    return 0


def print_guide() -> None:
    print(PRIVACY_NOTICE)
    print()
    print("微信聊天记录人格生成流程：")
    print("1. 先准备本地数据源（二选一）：")
    print("   - 已解密的 MSG.db / messages.sqlite；")
    print("   - wechat-dump-rs 等工具导出的本地目录。")
    print("2. 先跑 dry-run，确认能读到目标联系人消息：")
    print("   py -m tools.extract_wechat --wxid wxid_xxx --db \"D:\\path\\MSG.db\" --dry-run --verbose")
    print("3. 确认摘要正常后写入人格 JSON：")
    print("   py -m tools.extract_wechat --wxid wxid_xxx --db \"D:\\path\\MSG.db\" --name \"微信人格\" --out \"models\\personas\\wechat_persona.json\"")
    print("4. 也可以启动交互式向导：")
    print("   py -m tools.extract_wechat --wizard")
    print()
    print("可能的微信数据目录：")
    for path in discover_wechat_roots():
        print(f"- {path}")
    print("这些目录通常只能帮你确认账号位置；本工具仍需要你提供已解密数据库或导出目录。")


def run_wizard(args: argparse.Namespace) -> int:
    print(PRIVACY_NOTICE)
    print()
    roots = discover_wechat_roots()
    if roots:
        print("检测到可能的微信数据目录：")
        for index, root in enumerate(roots, 1):
            print(f"{index}. {root}")
        print()
    else:
        print("未自动找到微信数据目录；这不影响使用已导出的数据库或导出目录。")
        print()

    wxid = args.wxid or prompt_required("请输入要分析的联系人 wxid/标识")
    source_kind = prompt_choice("选择数据来源", ["已解密数据库文件", "导出目录"])
    db_paths = list(args.db)
    export_dir = args.export_dir

    if source_kind == "已解密数据库文件":
        if not db_paths:
            while True:
                path = prompt_required("请输入已解密 MSG.db/messages.sqlite 路径")
                db_paths.append(path)
                if input("还要添加另一个数据库吗？[y/N] ").strip().lower() != "y":
                    break
    elif not export_dir:
        export_dir = prompt_required("请输入 wechat-dump-rs 等工具的导出目录")

    display_name = args.name or input("生成人格显示名（直接回车则自动生成）：").strip() or None
    default_out = default_output_path(wxid)
    out = args.out or input(f"输出 JSON 路径（直接回车使用 {default_out}）：").strip() or str(default_out)

    dry_run_args = argparse.Namespace(
        wxid=wxid,
        db=db_paths,
        export_dir=export_dir,
        sqlcipher_key=args.sqlcipher_key,
        out=out,
        name=display_name,
        self_wxid=args.self_wxid,
        limit=args.limit,
        min_messages=args.min_messages,
        include_groups=args.include_groups,
        dry_run=True,
        overwrite=args.overwrite,
        quiet=True,
        verbose=True,
        guide=False,
        wizard=False,
    )
    print()
    print("先执行 dry-run 分析：")
    code = run(dry_run_args)
    if code != 0:
        return code

    if input("是否写入人格 JSON？[y/N] ").strip().lower() != "y":
        print("已取消写入。")
        return 0

    write_args = argparse.Namespace(**vars(dry_run_args))
    write_args.dry_run = False
    if Path(out).exists() and not args.overwrite:
        if input("输出文件已存在，是否覆盖？[y/N] ").strip().lower() != "y":
            print("已取消写入。")
            return 0
        write_args.overwrite = True
    return run(write_args)


def discover_wechat_roots() -> list[Path]:
    candidates = []
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidates.extend([
            Path(user_profile) / "Documents" / "WeChat Files",
            Path(user_profile) / "文档" / "WeChat Files",
        ])
    documents = os.environ.get("OneDrive")
    if documents:
        candidates.append(Path(documents) / "Documents" / "WeChat Files")
    candidates.extend([
        Path("F:/WeChat Files"),
        Path("F:/xwechat_files"),
    ])
    return [path for path in candidates if path.exists()]


def prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip().strip('"')
        if value:
            return value
        print("不能为空，请重新输入。")


def prompt_choice(label: str, choices: list[str]) -> str:
    print(label)
    for index, choice in enumerate(choices, 1):
        print(f"{index}. {choice}")
    while True:
        value = input("请输入序号: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(choices):
            return choices[int(value) - 1]
        print("选择无效，请重新输入。")


def default_output_path(wxid: str) -> Path:
    return PERSONAS_DIR / f"wechat_{safe_filename(wxid)}.json"


def safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe[:64] or "unknown"


def write_persona_json(persona: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(persona, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
