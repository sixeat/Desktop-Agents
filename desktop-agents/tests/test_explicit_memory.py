import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from core.explicit_memory import ExplicitMemoryStore


class ExplicitMemoryStoreTest(unittest.TestCase):
    def make_store(self, temp_dir: str) -> ExplicitMemoryStore:
        return ExplicitMemoryStore(Path(temp_dir) / "memory.sqlite3")

    def test_event_memory_for_tomorrow_exam_becomes_due_after_event(self):
        now = datetime(2026, 5, 26, 10, 0, 0)
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.make_store(temp_dir)
            records = store.remember_user_message("我明天要考试了", now=now)

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].category, "event")
            self.assertIn("考试", records[0].summary)
            self.assertEqual(datetime.fromtimestamp(records[0].event_time).date(), datetime(2026, 5, 27).date())

            due = store.due_memories(now=datetime(2026, 5, 28, 9, 0, 0))

        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].id, records[0].id)

    def test_compose_followup_for_yesterday_exam(self):
        now = datetime(2026, 5, 26, 10, 0, 0)
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.make_store(temp_dir)
            memory = store.remember_user_message("我明天要考试了", now=now)[0]
            followup = store.compose_followup(memory, now=datetime(2026, 5, 28, 9, 0, 0))

        self.assertIn("昨天", followup)
        self.assertIn("考试", followup)
        self.assertIn("怎么样", followup)

    def test_mark_mentioned_prevents_duplicate_due_recall(self):
        now = datetime(2026, 5, 26, 10, 0, 0)
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.make_store(temp_dir)
            memory = store.remember_user_message("我明天要考试了", now=now)[0]
            recall_time = datetime(2026, 5, 28, 9, 0, 0)

            self.assertEqual(len(store.due_memories(now=recall_time)), 1)
            store.mark_mentioned(memory.id, now=recall_time)
            due = store.due_memories(now=recall_time + timedelta(minutes=1))

        self.assertEqual(due, [])

    def test_preference_memory_is_extracted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.make_store(temp_dir)
            records = store.remember_user_message("我喜欢猫")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].category, "preference")
        self.assertEqual(records[0].summary, "喜欢猫")

    def test_plan_memory_is_extracted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.make_store(temp_dir)
            records = store.remember_user_message("我打算周末去爬山")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].category, "plan")
        self.assertIn("周末去爬山", records[0].summary)

    def test_fact_memory_is_extracted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.make_store(temp_dir)
            records = store.remember_user_message("我叫张三")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].category, "fact")
        self.assertEqual(records[0].summary, "名字是张三")

    def test_duplicate_memory_is_not_inserted_twice(self):
        now = datetime(2026, 5, 26, 10, 0, 0)
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.make_store(temp_dir)
            first = store.remember_user_message("我明天要考试了", now=now)[0]
            second = store.remember_user_message("我明天要考试了", now=now)[0]
            memories = store.relevant_memories(now=now, limit=10)

        self.assertEqual(first.id, second.id)
        self.assertEqual(len(memories), 1)

    def test_sensitive_text_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.make_store(temp_dir)
            records = store.remember_user_message("我的 api key 是 sk-abcdefghijklmnopqrstuvwxyz")

        self.assertEqual(records, [])

    def test_format_for_prompt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.make_store(temp_dir)
            memory = store.remember_user_message("我喜欢猫")[0]
            prompt = store.format_for_prompt([memory])

        self.assertIn("偏好", prompt)
        self.assertIn("喜欢猫", prompt)


if __name__ == "__main__":
    unittest.main()
