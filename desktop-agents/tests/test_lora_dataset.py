import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.lora_dataset import build_lora_dataset, format_lora_preview, is_noise_text, is_sensitive_text, read_lora_jsonl, sanitize_lora_text, write_lora_jsonl
from tools.export_lora_dataset import main
from tools.wechat.models import ChatMessage


class LoraDatasetTest(unittest.TestCase):
    def message(self, content: str, timestamp: int, target: bool) -> ChatMessage:
        return ChatMessage(None, "wxid_a", None, content, timestamp, target, 1, "test")

    def test_pairs_user_turn_with_next_target_reply(self):
        result = build_lora_dataset([
            self.message("今天好累", 1, False),
            self.message("辛苦啦，先休息一下", 2, True),
        ])

        self.assertEqual(result.stats.examples, 1)
        self.assertEqual(result.examples[0], {"messages": [{"role": "user", "content": "今天好累"}, {"role": "assistant", "content": "辛苦啦，先休息一下"}]})

    def test_skips_target_message_without_user_context(self):
        result = build_lora_dataset([
            self.message("我自己说一句", 1, True),
            self.message("今晚打球吗", 2, False),
            self.message("可以啊", 3, True),
        ])

        self.assertEqual(result.stats.examples, 1)
        self.assertEqual(result.stats.skipped_unpaired, 1)
        self.assertEqual(result.examples[0]["messages"][1]["content"], "可以啊")

    def test_sanitizes_media_url_and_sensitive_text(self):
        self.assertEqual(sanitize_lora_text("https://example.com 你好呀")[0], "你好呀")
        self.assertEqual(sanitize_lora_text("[图片]")[1], "empty")
        self.assertEqual(sanitize_lora_text("api key 是 sk-abcdefghijklmnopqrstuvwxyz")[1], "sensitive")
        self.assertTrue(is_sensitive_text("token abcdefghijklmnopqrstuvwxyz123456"))

    def test_filters_share_cards_and_placeholders_as_noise(self):
        self.assertTrue(is_noise_text("[其他消息]"))
        self.assertTrue(is_noise_text("[表情包：好耶]"))
        self.assertTrue(is_noise_text("【淘宝】 CZ057 商品链接"))
        self.assertTrue(is_noise_text("点击链接直接打开 或者 淘宝搜索直接打开"))
        self.assertEqual(sanitize_lora_text("[其他消息]")[1], "empty")

    def test_build_skips_sensitive_pairs(self):
        result = build_lora_dataset([
            self.message("我的验证码是 123456", 1, False),
            self.message("收到", 2, True),
            self.message("今天吃什么", 3, False),
            self.message("吃面吧", 4, True),
        ])

        self.assertEqual(result.stats.skipped_sensitive, 1)
        self.assertEqual(result.stats.examples, 1)
        self.assertEqual(result.examples[0]["messages"][0]["content"], "今天吃什么")

    def test_respects_min_chars_and_max_examples(self):
        result = build_lora_dataset([
            self.message("哈", 1, False),
            self.message("你好", 2, True),
            self.message("今天写代码", 3, False),
            self.message("可以", 4, True),
            self.message("继续吗", 5, False),
            self.message("继续", 6, True),
        ], min_user_chars=2, min_assistant_chars=2, max_examples=1)

        self.assertEqual(result.stats.examples, 1)
        self.assertEqual(result.stats.skipped_empty, 1)
        self.assertEqual(result.examples[0]["messages"][0]["content"], "今天写代码")

    def test_write_jsonl_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "train.jsonl"
            examples = [{"messages": [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好呀"}]}]

            stats = write_lora_jsonl(examples, path)
            self.assertEqual(stats.written, 1)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), examples[0])
            with self.assertRaises(FileExistsError):
                write_lora_jsonl(examples, path)

    def test_read_and_format_lora_preview(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "train.jsonl"
            examples = [{"messages": [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好呀"}]}]
            write_lora_jsonl(examples, path)

            loaded = read_lora_jsonl(path)
            preview = format_lora_preview(loaded, user_label="我", assistant_label="张斌")

        self.assertEqual(loaded, examples)
        self.assertEqual(preview, "[1]\n我：你好\n张斌：你好呀")

    def test_cli_dry_run_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "MSG.db"
            out_path = temp_path / "train.jsonl"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE MSG(LocalId INTEGER, StrTalker TEXT, StrContent TEXT, CreateTime INTEGER, IsSender INTEGER, Type INTEGER)")
            conn.execute("INSERT INTO MSG VALUES(1, 'wxid_a', '今晚打球吗', 1, 1, 1)")
            conn.execute("INSERT INTO MSG VALUES(2, 'wxid_a', '可以啊', 2, 0, 1)")
            conn.commit()
            conn.close()

            code = main(["--wxid", "wxid_a", "--db", str(db_path), "--out", str(out_path), "--dry-run", "--quiet"])

            self.assertEqual(code, 0)
            self.assertFalse(out_path.exists())

    def test_cli_writes_jsonl_and_requires_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "MSG.db"
            out_path = temp_path / "train.jsonl"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE MSG(LocalId INTEGER, StrTalker TEXT, StrContent TEXT, CreateTime INTEGER, IsSender INTEGER, Type INTEGER)")
            conn.execute("INSERT INTO MSG VALUES(1, 'wxid_a', '今晚打球吗', 1, 1, 1)")
            conn.execute("INSERT INTO MSG VALUES(2, 'wxid_a', '可以啊', 2, 0, 1)")
            conn.commit()
            conn.close()

            self.assertEqual(main(["--wxid", "wxid_a", "--db", str(db_path), "--out", str(out_path), "--quiet"]), 0)
            self.assertTrue(out_path.exists())
            self.assertEqual(main(["--wxid", "wxid_a", "--db", str(db_path), "--out", str(out_path), "--quiet"]), 1)
            self.assertEqual(main(["--wxid", "wxid_a", "--db", str(db_path), "--out", str(out_path), "--overwrite", "--quiet"]), 0)


if __name__ == "__main__":
    unittest.main()
