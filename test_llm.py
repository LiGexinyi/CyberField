"""LLM 客户端输入输出边界：null/空/非字符串内容不得冒充成功总结。

只使用假响应，不调用真实模型或读取凭据。
"""
import json
import unittest
from unittest.mock import patch

from collect.llm import chat


class LlmOutputBoundaryTests(unittest.TestCase):
    """伪造 urlopen 返回各类响应，验证 chat 的返回类型与空值处理。"""

    def _fake_urlopen(self, payload):
        """构造带 with 协议的假响应对象。"""
        class FakeResponse:
            """仅提供 read 与上下文协议的最小响应。"""
            def __init__(self, data):
                """预编码响应体。"""
                self._data = data
            def __enter__(self):
                """进入 with 块。"""
                return self
            def __exit__(self, *args):
                """退出 with 块。"""
                return False
            def read(self):
                """返回响应体字节。"""
                return self._data
        body = json.dumps(payload).encode("utf-8")
        return patch("collect.llm.urllib.request.urlopen",
                     return_value=FakeResponse(body))

    def _config(self):
        """固定的假配置，避免读取真实环境变量。"""
        return patch("collect.llm.config", return_value={
            "key": "fake-key", "base": "https://example.invalid/v1",
            "model": "fake-model"})

    def _chat(self, payload):
        """按给定模型响应执行一次 chat。"""
        with self._config(), self._fake_urlopen(payload):
            return chat([{"role": "user", "content": "hi"}])

    def test_null_content_returns_none(self):
        """choices[0].message.content 为 null 时返回 None。"""
        self.assertIsNone(self._chat({"choices": [{"message": {"content": None}}]}))

    def test_empty_string_returns_none(self):
        """content 为空串（含空白）时返回 None。"""
        self.assertIsNone(self._chat({"choices": [{"message": {"content": "   "}}]}))

    def test_non_string_content_returns_none(self):
        """content 是数字等非字符串时返回 None。"""
        self.assertIsNone(self._chat({"choices": [{"message": {"content": 123}}]}))

    def test_valid_string_returns_stripped(self):
        """正常字符串去掉首尾空白后返回。"""
        self.assertEqual(
            self._chat({"choices": [{"message": {"content": "  好的总结  "}}]}),
            "好的总结")

    def test_missing_choices_or_message_returns_none(self):
        """缺 choices / message / content 均返回 None。"""
        for payload in ({}, {"choices": []},
                        {"choices": [{}]},
                        {"choices": [{"message": {}}]}):
            with self.subTest(payload=payload):
                self.assertIsNone(self._chat(payload))


if __name__ == "__main__":
    unittest.main()
