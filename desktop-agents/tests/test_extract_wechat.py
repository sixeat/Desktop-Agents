import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.importer.wechat_importer import WeChatImporter
from core.personality import Personality
from tools.extract_wechat import main
from tools.wechat.analyzer import build_personality
from tools.wechat.models import ChatMessage
from tools.wechat.parsers import load_export_dir, load_messages


class ExtractWechatTest(unittest.TestCase):
    def test_analyzer_outputs_personality_json_compatible_with_runtime(self):
        messages = [
            ChatMessage(None, "wxid_a", None, "哈哈这个 bug 有点离谱！", 1, True, 1, "test"),
            ChatMessage(None, "wxid_a", None, "先看日志，再看接口。", 2, True, 1, "test"),
            ChatMessage(None, "wxid_a", None, "Python 这段代码可以优化一下", 3, True, 1, "test"),
            ChatMessage(None, "wxid_a", None, "今天项目会议几点？", 4, True, 1, "test"),
        ]

        persona = build_personality(messages, "wxid_a", display_name="微信人格")

        self.assertEqual(persona["name"], "微信人格")
        self.assertIn("style", persona)
        self.assertIn("topics", persona)
        self.assertIn(persona["emoji_frequency"], {"low", "medium", "high"})

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "wechat_persona.json"
            path.write_text(json.dumps(persona, ensure_ascii=False), encoding="utf-8")
            personality = Personality.from_json(path)
            self.assertEqual(personality.name, "微信人格")
            self.assertIn("微信人格", personality.build_system_prompt())

    def test_parses_msg_schema_and_filters_non_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "MSG.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE MSG(LocalId INTEGER, StrTalker TEXT, StrContent TEXT, CreateTime INTEGER, IsSender INTEGER, Type INTEGER)")
            conn.execute("INSERT INTO MSG VALUES(1, 'wxid_a', '你好呀', 1, 0, 1)")
            conn.execute("INSERT INTO MSG VALUES(2, 'wxid_a', '<msg><appmsg /></msg>', 2, 0, 1)")
            conn.execute("INSERT INTO MSG VALUES(3, 'wxid_b', '不相关', 3, 0, 1)")
            conn.execute("INSERT INTO MSG VALUES(4, 'wxid_a', '[图片]', 4, 0, 1)")
            conn.execute("INSERT INTO MSG VALUES(5, 'wxid_a', '我这边回复', 5, 1, 1)")
            conn.commit()
            conn.close()

            messages, report = load_messages([db_path], "wxid_a")

        self.assertEqual([message.content for message in messages], ["你好呀", "我这边回复"])
        self.assertTrue(messages[0].is_from_target)
        self.assertFalse(messages[1].is_from_target)
        self.assertEqual(report.total_messages, 2)

    def test_parses_alternate_messages_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "messages.sqlite"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE messages(id INTEGER, talker TEXT, content TEXT, timestamp INTEGER, type INTEGER)")
            conn.execute("INSERT INTO messages VALUES(1, 'wxid_a', '今天工作挺忙', 1, 1)")
            conn.execute("INSERT INTO messages VALUES(2, 'wxid_a', '语音消息', 2, 34)")
            conn.commit()
            conn.close()

            messages, report = load_messages([db_path], "wxid_a")

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].content, "今天工作挺忙")

    def test_wechat_importer_full_import_from_wx_mcp(self):
        class FakeMCP:
            def installed(self):
                return True

            def ready(self):
                return True

            def contacts(self, limit=200):
                return [{"id": "session_a", "display_name": "张斌", "message_count": 8, "type": "private"}]

            def messages(self, session, limit=5000):
                return [
                    {"content": "今晚打球吗", "sender": "张斌", "time": 1, "is_from_me": False, "type": "text"},
                    {"content": "可以啊", "sender": "我", "time": 2, "is_from_me": True, "type": "text"},
                    {"content": "那我晚点到", "sender": "张斌", "time": 3, "is_from_me": False, "type": "text"},
                    {"content": "你先过去", "sender": "张斌", "time": 4, "is_from_me": False, "type": "text"},
                    {"content": "我马上", "sender": "张斌", "time": 5, "is_from_me": False, "type": "text"},
                    {"content": "别急", "sender": "张斌", "time": 6, "is_from_me": False, "type": "text"},
                    {"content": "到了说", "sender": "张斌", "time": 7, "is_from_me": False, "type": "text"},
                ]

        with tempfile.TemporaryDirectory() as temp_dir:
            persona_dir = Path(temp_dir) / "personas"
            importer = WeChatImporter(output_dir=persona_dir)
            importer.mcp = FakeMCP()

            contacts = importer.contacts()
            result = importer.full_import("session_a", "张斌")
            persona_exists = (persona_dir / "张斌.json").exists()

        self.assertEqual(contacts[0]["name"], "张斌")
        self.assertIsNotNone(result)
        self.assertTrue(persona_exists)

    def test_parses_wechatmsg_csv_export(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)
            csv_path = export_dir / "zhangbin91009.csv"
            csv_path.write_text(
                "id,MsgSvrID,type_name,is_sender,talker,room_name,content,CreateTime\n"
                "1,100,文字,0,zhangbin91009,,{\"msg\": \"今晚打球吗\"},2024-01-01 10:00:00\n"
                "2,101,图片,0,zhangbin91009,,{\"msg\": \"[图片]\"},2024-01-01 10:01:00\n",
                encoding="utf-8",
            )

            messages, report = load_export_dir(export_dir, "zhangbin91009")

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].content, "今晚打球吗")
        self.assertEqual(report.target_messages, 1)

    def test_wechat_importer_imports_local_export_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "zhangbin91009.csv"
            csv_path.write_text(
                "id,MsgSvrID,type_name,is_sender,talker,room_name,content,CreateTime\n"
                "1,100,文字,0,zhangbin91009,,{\"msg\": \"今晚打球吗\"},2024-01-01 10:00:00\n"
                "2,101,文字,0,zhangbin91009,,{\"msg\": \"我晚点到\"},2024-01-01 10:01:00\n"
                "3,102,文字,0,zhangbin91009,,{\"msg\": \"你先过去\"},2024-01-01 10:02:00\n"
                "4,103,文字,0,zhangbin91009,,{\"msg\": \"别急\"},2024-01-01 10:03:00\n"
                "5,104,文字,0,zhangbin91009,,{\"msg\": \"到了说\"},2024-01-01 10:04:00\n",
                encoding="utf-8",
            )
            persona_dir = temp_path / "personas"
            importer = WeChatImporter(output_dir=persona_dir)

            result = importer.import_export_path(csv_path, "zhangbin91009", "张斌")

            self.assertIsNotNone(result)
            self.assertTrue((persona_dir / "张斌.json").exists())

    def test_cli_guide_does_not_require_wxid(self):
        code = main(["--guide"])

        self.assertEqual(code, 0)

    def test_cli_requires_wxid_without_guide_or_wizard(self):
        code = main(["--dry-run", "--quiet"])

        self.assertEqual(code, 1)

    def test_cli_dry_run_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "MSG.db"
            out_path = temp_path / "persona.json"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE MSG(LocalId INTEGER, StrTalker TEXT, StrContent TEXT, CreateTime INTEGER, IsSender INTEGER, Type INTEGER)")
            conn.execute("INSERT INTO MSG VALUES(1, 'wxid_a', '哈哈今天写代码', 1, 0, 1)")
            conn.execute("INSERT INTO MSG VALUES(2, 'wxid_a', '这个接口有 bug', 2, 0, 1)")
            conn.commit()
            conn.close()

            code = main([
                "--wxid", "wxid_a",
                "--db", str(db_path),
                "--out", str(out_path),
                "--dry-run",
                "--quiet",
            ])

            self.assertEqual(code, 0)
            self.assertFalse(out_path.exists())


if __name__ == "__main__":
    unittest.main()
