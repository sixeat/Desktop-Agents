import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import train_lora


class FakeCuda:
    @staticmethod
    def is_available():
        return False


class FakeTorch:
    cuda = FakeCuda()


class TrainLoraTest(unittest.TestCase):
    def write_dataset(self, path: Path, rows=None) -> None:
        rows = rows or [{"messages": [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好呀"}]}]
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")

    def test_module_imports_without_training_dependencies(self):
        self.assertTrue(hasattr(train_lora, "main"))

    def test_validate_only_accepts_valid_dataset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = Path(temp_dir) / "train.jsonl"
            self.write_dataset(dataset)

            code = train_lora.main(["--dataset", str(dataset), "--validate-only"])

        self.assertEqual(code, 0)

    def test_validate_only_rejects_invalid_dataset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = Path(temp_dir) / "bad.jsonl"
            self.write_dataset(dataset, [{"messages": [{"role": "user", "content": "你好"}]}])

            code = train_lora.main(["--dataset", str(dataset), "--validate-only"])

        self.assertEqual(code, 1)

    def test_dry_run_checks_dependencies_without_creating_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dataset = temp_path / "train.jsonl"
            output = temp_path / "adapter"
            self.write_dataset(dataset)
            fake_deps = train_lora.TrainingDependencies(
                torch=FakeTorch(),
                AutoModelForCausalLM=None,
                AutoTokenizer=None,
                DataCollatorForLanguageModeling=None,
                Trainer=None,
                TrainingArguments=None,
                LoraConfig=None,
                get_peft_model=None,
            )

            with patch("tools.train_lora.load_training_dependencies", return_value=fake_deps):
                code = train_lora.main(["--dataset", str(dataset), "--out", str(output), "--dry-run"])

        self.assertEqual(code, 0)
        self.assertFalse(output.exists())

    def test_missing_training_dependencies_returns_guidance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = Path(temp_dir) / "train.jsonl"
            self.write_dataset(dataset)

            with patch("tools.train_lora.load_training_dependencies", side_effect=train_lora.MissingTrainingDependency()):
                code = train_lora.main(["--dataset", str(dataset), "--dry-run"])

        self.assertEqual(code, 2)

    def test_existing_output_dir_requires_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dataset = temp_path / "train.jsonl"
            output = temp_path / "adapter"
            output.mkdir()
            (output / "old.txt").write_text("old", encoding="utf-8")
            self.write_dataset(dataset)

            code = train_lora.main(["--dataset", str(dataset), "--out", str(output), "--validate-only"])

        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
