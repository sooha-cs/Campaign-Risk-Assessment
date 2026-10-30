"""Fences, Pydantic rejection + retry with error feedback, caching, timeout, empty input. AI mocked."""
import copy
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import ai_service  # noqa: E402
from app import app  # noqa: E402
from groq_client import GroqError  # noqa: E402
from test_offline import GOOD_PLAN, GOOD_RISKS, PROJECT, fake_ai  # noqa: E402


class Hardening(unittest.TestCase):
    def setUp(self):
        ai_service.cache_clear()
        self.c = app.test_client()
        with fake_ai(GOOD_PLAN):
            self.plan = self.c.post("/api/plan", json=PROJECT).get_json()
        self.body = {"project": PROJECT, "plan": self.plan}

    def test_code_fences_are_stripped(self):
        with fake_ai("```json\n" + json.dumps(GOOD_RISKS) + "\n```"):
            self.assertEqual(self.c.post("/api/analyze", json=self.body).status_code, 200)

    def test_out_of_range_is_rejected_and_error_is_fed_back(self):
        bad = copy.deepcopy(GOOD_RISKS)
        bad["risks"][0]["probability"] = 7
        with fake_ai(bad, GOOD_RISKS) as m:
            r = self.c.post("/api/analyze", json=self.body)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(m.call_count, 2)
        retry_prompt = m.call_args_list[1].args[0][1]["content"]
        self.assertIn("rejected", retry_prompt)
        self.assertIn("probability", retry_prompt)

    def test_gives_up_after_two_retries(self):
        bad = copy.deepcopy(GOOD_RISKS)
        bad["risks"][0]["category"] = "Weather"
        with fake_ai(bad, bad, bad) as m:
            r = self.c.post("/api/analyze", json=self.body)
        self.assertEqual(r.status_code, 502)
        self.assertEqual(m.call_count, 3)

    def test_cache_hit_and_nocache(self):
        with fake_ai(GOOD_RISKS, GOOD_RISKS) as m:
            a = self.c.post("/api/analyze", json=self.body).get_json()
            b = self.c.post("/api/analyze", json=self.body).get_json()
            self.assertEqual(m.call_count, 1)
            self.assertEqual(a, b)
            self.c.post("/api/analyze?nocache=1", json=self.body)
            self.assertEqual(m.call_count, 2)

    def test_timeout_gives_504(self):
        with mock.patch.object(ai_service, "call_groq", side_effect=GroqError("timed out", 504)), \
                mock.patch("ai_service.time.sleep"):
            r = self.c.post("/api/analyze", json=self.body)
        self.assertEqual(r.status_code, 504)

    def test_empty_input_gives_400(self):
        self.assertEqual(self.c.post("/api/analyze", json={}).status_code, 400)
        self.assertEqual(self.c.post("/api/analyze", data="").status_code, 400)


if __name__ == "__main__":
    unittest.main()