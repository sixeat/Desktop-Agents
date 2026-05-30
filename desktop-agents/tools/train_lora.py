import argparse
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.lora_dataset import read_lora_jsonl

DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
TRAINING_DEPENDENCY_HELP = """
缺少 LoRA 训练依赖。请运行：
python -m pip install -r requirements-train.txt

如需 CUDA 版 PyTorch，请先按 https://pytorch.org/get-started/locally/ 安装匹配版本。
""".strip()


class DatasetValidationError(ValueError):
    pass


class MissingTrainingDependency(RuntimeError):
    pass


@dataclass(frozen=True)
class DatasetSummary:
    examples: int
    avg_user_chars: float
    avg_assistant_chars: float
    max_user_chars: int
    max_assistant_chars: int

    @property
    def recommendation(self) -> str:
        if self.examples < 100:
            return "样本少于 100 条，不建议训练。"
        if self.examples < 500:
            return "样本量可以试训，但效果可能不稳定。"
        return "样本量适合第一版 LoRA 试训。"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except MissingTrainingDependency:
        print(TRAINING_DEPENDENCY_HELP, file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 ChatML JSONL 训练 LoRA adapter")
    parser.add_argument("--dataset", required=True, help="LoRA 训练 JSONL 路径")
    parser.add_argument("--out", help="输出 adapter 目录，默认 models/lora_adapters/<dataset-stem>")
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL, help=f"基础模型，默认 {DEFAULT_BASE_MODEL}")
    parser.add_argument("--epochs", type=float, default=3.0, help="训练轮数，默认 3")
    parser.add_argument("--rank", type=int, default=8, help="LoRA rank，默认 8")
    parser.add_argument("--batch-size", type=int, default=1, help="单设备 batch size，默认 1")
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8, help="梯度累积步数，默认 8")
    parser.add_argument("--learning-rate", type=float, default=2e-4, help="学习率，默认 2e-4")
    parser.add_argument("--max-length", type=int, default=512, help="最大 token 长度，默认 512")
    parser.add_argument("--validate-only", action="store_true", help="只校验数据集，不检查训练依赖、不训练")
    parser.add_argument("--dry-run", action="store_true", help="校验数据并检查训练依赖，不下载模型、不训练")
    parser.add_argument("--overwrite", action="store_true", help="允许使用已有输出目录")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    dataset_path = Path(args.dataset)
    examples = read_lora_jsonl(dataset_path)
    summary = validate_lora_examples(examples)
    print_dataset_summary(summary)

    output_dir = Path(args.out) if args.out else default_output_dir(dataset_path)
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"输出目录已存在且非空：{output_dir}。如需继续请加 --overwrite。")

    if args.validate_only:
        print("validate-only 模式：数据集格式有效，未检查训练依赖，未训练。")
        return 0

    if args.dry_run:
        deps = load_training_dependencies()
        print_training_config(args, output_dir, deps.torch)
        print("dry-run 模式：已检查训练依赖，未下载模型，未训练。")
        return 0

    deps = load_training_dependencies()
    train_lora(args, examples, output_dir, deps)
    return 0


def default_output_dir(dataset_path: Path) -> Path:
    return Path("models") / "lora_adapters" / dataset_path.stem


def validate_lora_examples(examples: list[dict[str, Any]]) -> DatasetSummary:
    if not examples:
        raise DatasetValidationError("数据集为空。")

    user_lengths = []
    assistant_lengths = []
    for index, example in enumerate(examples, 1):
        messages = example.get("messages")
        if not isinstance(messages, list):
            raise DatasetValidationError(f"第 {index} 条样本缺少 messages 列表。")
        user_messages = [message for message in messages if isinstance(message, dict) and message.get("role") == "user"]
        assistant_messages = [message for message in messages if isinstance(message, dict) and message.get("role") == "assistant"]
        if not user_messages or not assistant_messages:
            raise DatasetValidationError(f"第 {index} 条样本必须同时包含 user 和 assistant 消息。")
        user_text = str(user_messages[-1].get("content") or "").strip()
        assistant_text = str(assistant_messages[-1].get("content") or "").strip()
        if not user_text or not assistant_text:
            raise DatasetValidationError(f"第 {index} 条样本包含空 content。")
        user_lengths.append(len(user_text))
        assistant_lengths.append(len(assistant_text))

    return DatasetSummary(
        examples=len(examples),
        avg_user_chars=statistics.mean(user_lengths),
        avg_assistant_chars=statistics.mean(assistant_lengths),
        max_user_chars=max(user_lengths),
        max_assistant_chars=max(assistant_lengths),
    )


def print_dataset_summary(summary: DatasetSummary) -> None:
    print("LoRA 训练数据摘要：")
    print(f"- 样本数：{summary.examples}")
    print(f"- user 平均字符数：{summary.avg_user_chars:.1f}")
    print(f"- assistant 平均字符数：{summary.avg_assistant_chars:.1f}")
    print(f"- user 最大字符数：{summary.max_user_chars}")
    print(f"- assistant 最大字符数：{summary.max_assistant_chars}")
    print(f"- 建议：{summary.recommendation}")


def print_training_config(args: argparse.Namespace, output_dir: Path, torch_module) -> None:
    cuda_available = bool(torch_module.cuda.is_available())
    print("LoRA 训练配置：")
    print(f"- base model：{args.base_model}")
    print(f"- 输出目录：{output_dir}")
    print(f"- epochs：{args.epochs}")
    print(f"- rank：{args.rank}")
    print(f"- batch size：{args.batch_size}")
    print(f"- gradient accumulation：{args.gradient_accumulation_steps}")
    print(f"- learning rate：{args.learning_rate}")
    print(f"- max length：{args.max_length}")
    print(f"- CUDA：{'可用' if cuda_available else '不可用，将使用 CPU（会很慢）'}")


@dataclass(frozen=True)
class TrainingDependencies:
    torch: Any
    AutoModelForCausalLM: Any
    AutoTokenizer: Any
    DataCollatorForLanguageModeling: Any
    Trainer: Any
    TrainingArguments: Any
    LoraConfig: Any
    get_peft_model: Any


def load_training_dependencies() -> TrainingDependencies:
    try:
        import torch
        from peft import LoraConfig, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, DataCollatorForLanguageModeling, Trainer, TrainingArguments
    except ImportError as exc:
        raise MissingTrainingDependency() from exc
    return TrainingDependencies(
        torch=torch,
        AutoModelForCausalLM=AutoModelForCausalLM,
        AutoTokenizer=AutoTokenizer,
        DataCollatorForLanguageModeling=DataCollatorForLanguageModeling,
        Trainer=Trainer,
        TrainingArguments=TrainingArguments,
        LoraConfig=LoraConfig,
        get_peft_model=get_peft_model,
    )


def train_lora(args: argparse.Namespace, examples: list[dict[str, Any]], output_dir: Path, deps: TrainingDependencies) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = deps.AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    texts = [tokenizer.apply_chat_template(example["messages"], tokenize=False, add_generation_prompt=False) for example in examples]
    tokenized = tokenizer(texts, truncation=True, max_length=args.max_length)
    dataset = [{"input_ids": input_ids, "attention_mask": attention_mask, "labels": list(input_ids)} for input_ids, attention_mask in zip(tokenized["input_ids"], tokenized["attention_mask"])]

    use_cuda = deps.torch.cuda.is_available()
    torch_dtype = deps.torch.bfloat16 if use_cuda and deps.torch.cuda.is_bf16_supported() else deps.torch.float16 if use_cuda else deps.torch.float32
    model_kwargs = {"torch_dtype": torch_dtype, "trust_remote_code": True}
    if use_cuda:
        model_kwargs["device_map"] = "auto"
    model = deps.AutoModelForCausalLM.from_pretrained(args.base_model, **model_kwargs)
    lora_config = deps.LoraConfig(
        r=args.rank,
        lora_alpha=args.rank * 2,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = deps.get_peft_model(model, lora_config)
    data_collator = deps.DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)
    training_args = deps.TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        logging_steps=10,
        save_strategy="epoch",
        report_to=[],
    )
    trainer = deps.Trainer(model=model, args=training_args, train_dataset=dataset, data_collator=data_collator)
    trainer.train()
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"已保存 LoRA adapter：{output_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
