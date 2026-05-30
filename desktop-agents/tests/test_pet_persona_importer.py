import json
import tempfile
import unittest
from pathlib import Path

from core.pet_persona_importer import BatchPersonaPlan, PersonaPackageMetadata, build_persona_package_preview, build_batch_personas, load_profile_from_export, safe_persona_slug, save_pet_persona, save_pet_persona_package, scan_persona_sources
from core.personality_trainer import PersonalityProfile, PersonalityTrainer


class PetPersonaImporterTest(unittest.TestCase):
    def test_load_profile_from_txt_export_uses_custom_persona_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "张斌.txt"
            lines = []
            for index in range(12):
                lines.append(f"2024-01-01 10:{index:02d}:00 张斌 [文字] 哈哈今天打球真开心{index}")
            lines.append("2024-01-01 11:00:00 槐 [文字] 可以啊")
            path.write_text("\n".join(lines), encoding="utf-8")

            result = load_profile_from_export(path, target_name="张斌", pet_name="奶糖", pet_type="cat")

        self.assertEqual(result.profile.name, "奶糖")
        self.assertEqual(result.profile.pet_type, "cat")
        self.assertEqual(result.target_message_count, 12)
        self.assertEqual(result.message_count, 12)
        self.assertFalse(result.used_fallback_messages)
        self.assertTrue(result.profile.system_prompt)

    def test_load_profile_from_csv_export_falls_back_when_target_messages_are_few(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "朋友.csv"
            path.write_text(
                "talker,sender,content,is_sender,time,type\n"
                "朋友,朋友,收到我晚点看看,0,2024-01-01 10:00:00,text\n"
                "朋友,我,好的,1,2024-01-01 10:01:00,text\n"
                "朋友,我,这个方案可以先试试,1,2024-01-01 10:02:00,text\n",
                encoding="utf-8-sig",
            )

            result = load_profile_from_export(path, target_name="朋友", pet_name="布丁", pet_type="dog")

        self.assertEqual(result.target_message_count, 1)
        self.assertEqual(result.message_count, 3)
        self.assertTrue(result.used_fallback_messages)
        self.assertTrue(result.profile.catchphrases)

    def test_load_profile_from_json_export(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "可可.json"
            data = {"messages": [
                {"talker": "可可", "sender": "可可", "content": "早呀今天也加油", "timestamp": 1, "type": 1},
                {"talker": "可可", "sender": "可可", "content": "哈哈这个好有意思", "timestamp": 2, "type": 1},
                {"talker": "可可", "sender": 1, "content": "是的", "timestamp": 3, "type": 1},
            ]}
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            result = load_profile_from_export(path, target_name="可可", pet_name="可可", pet_type="rabbit", minimum_target_messages=2)

        self.assertEqual(result.target_message_count, 2)
        self.assertEqual(result.message_count, 2)
        self.assertFalse(result.used_fallback_messages)
        self.assertEqual(result.profile.pet_type, "rabbit")

    def test_safe_slug_and_save_pet_persona(self):
        profile = PersonalityTrainer().analyze(["你好呀哈哈"], pet_name="奶糖", pet_type="cat")

        with tempfile.TemporaryDirectory() as temp_dir:
            output = save_pet_persona(profile, Path(temp_dir) / safe_persona_slug("奶 糖!") / "persona.json")
            loaded = PersonalityTrainer.load(output)

        self.assertEqual(output.name, "persona.json")
        self.assertEqual(loaded.name, "奶糖")
        self.assertEqual(safe_persona_slug("奶 糖!"), "奶_糖")

    def test_persona_package_preview_has_privacy_flags_without_writing_files(self):
        profile = PersonalityProfile(
            name="朋友",
            pet_type="cat",
            personality_tag="活泼",
            catchphrases=["电话13812345678"],
            sentence_patterns=[],
            emoji_habits=[],
            topics=["日常"],
            avg_sentence_length=5.0,
            greeting_style="直接开聊",
            system_prompt="你是朋友。",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "朋友"
            preview = build_persona_package_preview(
                profile,
                PersonaPackageMetadata(message_count=3, target_message_count=2, used_fallback_messages=True),
            )

            self.assertFalse(package_dir.exists())

        self.assertIn("manifest.json", preview["files"])
        self.assertIn("examples.jsonl", preview["files"])
        self.assertFalse(preview["manifest"]["privacy"]["raw_chat_included"])
        self.assertTrue(preview["manifest"]["privacy"]["local_only_default"])
        self.assertFalse(preview["manifest"]["privacy"]["cloud_enhancement_enabled"])
        self.assertTrue(preview["manifest"]["privacy"]["contains_anonymized_training_seed"])
        self.assertEqual(preview["manifest"]["message_count"], 3)
        self.assertTrue(preview["manifest"]["used_fallback_messages"])
        self.assertGreater(preview["manifest"]["privacy"]["blocked_sensitive_patterns"], 0)

    def test_save_pet_persona_package_writes_scrubbed_artifacts(self):
        profile = PersonalityTrainer().analyze(
            ["我的手机号是13812345678，邮箱是friend@example.com，住在上海市浦东新区。哈哈收到"],
            pet_name="朋友",
            pet_type="cat",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            persona_path = save_pet_persona_package(
                profile,
                Path(temp_dir) / "朋友",
                PersonaPackageMetadata(message_count=12, target_message_count=10, used_fallback_messages=False),
            )
            package_dir = persona_path.parent
            files = {path.name for path in package_dir.iterdir()}
            combined = "\n".join(path.read_text(encoding="utf-8") for path in package_dir.iterdir())
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            eval_report = json.loads((package_dir / "eval_report.json").read_text(encoding="utf-8"))

        self.assertEqual({"manifest.json", "persona.json", "style_profile.json", "examples.jsonl", "system_prompt.txt", "eval_report.json"}, files)
        self.assertNotIn("13812345678", combined)
        self.assertNotIn("friend@example.com", combined)
        self.assertNotIn("上海市浦东新区", combined)
        self.assertEqual(manifest["message_count"], 12)
        self.assertFalse(manifest["privacy"]["raw_chat_included"])
        self.assertTrue(manifest["privacy"]["contains_anonymized_training_seed"])
        self.assertFalse(eval_report["privacy_checks"]["claims_real_person"])
        self.assertGreater(eval_report["privacy_checks"]["blocked_sensitive_patterns"], 0)

    def test_scan_sources_discovers_private_and_group_senders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "私聊_张斌.txt").write_text(
                "2024-01-01 10:00:00 '张斌'\n今晚打球吗\n\n"
                "2024-01-01 10:01:00 '我'\n可以\n\n"
                "2024-01-01 10:02:00 '张斌'\n那我晚点到\n",
                encoding="utf-8",
            )
            (folder / "群聊_AAA.txt").write_text(
                "2024-01-01 11:00:00 '张斌'\n你们到了没\n\n"
                "2024-01-01 11:01:00 '老猪'\n快了快了\n\n"
                "2024-01-01 11:02:00 '老猪'\n别催\n",
                encoding="utf-8",
            )

            sources = scan_persona_sources(folder, minimum_messages=2)

        by_name = {source.name: source for source in sources}
        self.assertEqual(by_name["张斌"].message_count, 3)
        self.assertEqual(by_name["老猪"].message_count, 2)
        self.assertNotIn("我", by_name)

    def test_scan_sources_ignores_group_name_system_sender(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "群聊_AAA.txt").write_text(
                "2024-01-01 10:00:00 'AAA'\n某人加入了群聊\n\n"
                "2024-01-01 10:01:00 'AAA'\n请注意隐私安全\n\n"
                "2024-01-01 10:02:00 '张斌'\n今晚打球吗\n\n"
                "2024-01-01 10:03:00 '张斌'\n我快到了\n",
                encoding="utf-8",
            )

            sources = scan_persona_sources(folder, minimum_messages=2)

        self.assertEqual([source.name for source in sources], ["张斌"])

    def test_build_batch_personas_can_merge_aliases_and_save(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "exports"
            folder.mkdir()
            (folder / "群聊_AAA.txt").write_text(
                "2024-01-01 11:00:00 '张斌'\n你们到了没\n\n"
                "2024-01-01 11:01:00 '斌哥'\n哈哈我也快到了\n",
                encoding="utf-8",
            )
            sources = scan_persona_sources(folder, minimum_messages=1)
            output_dir = Path(temp_dir) / "personas"

            results = build_batch_personas(
                sources,
                [BatchPersonaPlan(persona_name="张斌", source_names=["张斌", "斌哥"], pet_type="dog")],
                output_dir=output_dir,
            )
            manifest_exists = (results[0].output_path.parent / "manifest.json").exists()

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].profile.name, "张斌")
            self.assertEqual(results[0].profile.pet_type, "dog")
            self.assertEqual(results[0].message_count, 2)
            self.assertEqual(results[0].output_path.name, "persona.json")
            self.assertTrue(manifest_exists)


if __name__ == "__main__":
    unittest.main()
