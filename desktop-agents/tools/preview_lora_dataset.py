import argparse
import sys

from core.lora_dataset import format_lora_preview, read_lora_jsonl


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        examples = read_lora_jsonl(args.dataset, limit=args.limit)
        if not examples:
            print("未读取到 LoRA 样本。", file=sys.stderr)
            return 2
        print(format_lora_preview(examples, user_label=args.user_label, assistant_label=args.assistant_label))
        return 0
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="预览 LoRA JSONL 训练样本")
    parser.add_argument("dataset", help="LoRA JSONL 路径")
    parser.add_argument("--limit", type=int, default=20, help="预览样本数量，默认 20")
    parser.add_argument("--user-label", default="你", help="user 侧显示名")
    parser.add_argument("--assistant-label", default="目标", help="assistant 侧显示名")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
