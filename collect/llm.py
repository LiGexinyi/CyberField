"""LLM 客户端：OpenAI 兼容接口（默认 DeepSeek），用于内容总结与关键词扩展。

设计：
    - 纯标准库（urllib），无第三方依赖；
    - 从环境变量读取配置：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL；
    - 没有 API Key 时所有函数静默返回 None（调用方降级为本地摘要），
      不阻塞搜索流程；
    - 任何请求失败都降级返回 None，绝不抛出中断采集/搜索。
"""

import json
import logging
import os
import urllib.request
from collect import settings

logger = logging.getLogger(__name__)

_DEFAULT_BASE = settings.DEFAULT_LLM_BASE
_DEFAULT_MODEL = settings.DEFAULT_LLM_MODEL


def config() -> dict:
    """读取 LLM 配置（每次调用读取，便于运行时注入环境变量后重启生效）。"""
    return {
        "key": os.environ.get("LLM_API_KEY", "").strip(),
        "base": os.environ.get("LLM_BASE_URL", _DEFAULT_BASE).strip().rstrip("/"),
        "model": os.environ.get("LLM_MODEL", _DEFAULT_MODEL).strip(),
    }


def available() -> bool:
    """是否配置了可用 API Key。"""
    return bool(config()["key"])


def chat(messages: list[dict], max_tokens: int = 500,
         temperature: float = 0.4) -> str | None:
    """调用 OpenAI 兼容 chat/completions，成功返回内容，失败返回 None。"""
    cfg = config()
    if not cfg["key"]:
        return None
    payload = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        cfg["base"] + "/chat/completions", data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + cfg["key"]},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # 严格校验返回内容：null / 空串 / 非字符串一律视为失败，绝不能
        # 把 "None" 之类的字符串当成成功总结返回。
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = (message or {}).get("content")
        if not isinstance(content, str):
            return None
        return content.strip() or None
    except Exception:
        # 调用方按 None 降级；失败原因（超时/4xx/解析）留日志便于排查。
        logger.debug("LLM 请求失败，按无总结降级", exc_info=True)
        return None


def summarize_post(title: str, text: str,
                   comments: list[str] | None = None,
                   platform: str = "") -> str | None:
    """生成一小段内容总结（原帖 + 评论区）。无 Key 返回 None。"""
    if not available():
        return None
    prompt = f"标题：{title or '（无标题）'}\n正文：{(text or '').strip()[:800]}"
    if comments:
        prompt += "\n热门评论：\n" + "\n".join(f"- {c}" for c in comments[:5])
    messages = [
        {"role": "system",
         "content": "你是网络文化观察助手。用不超过 120 字、客观克制的中文，概括这条内容"
                    "在讲什么、评论区在讨论什么。不评判好坏、不站队。只输出总结本身，"
                    "不要任何前缀或标题。"},
        {"role": "user", "content": prompt},
    ]
    return chat(messages, max_tokens=220)


def expand_keywords(word: str) -> list[str]:
    """用 LLM 扩展相关搜索词（模糊搜索）。无 Key 返回 [word]。"""
    if not available():
        return [word]
    messages = [
        {"role": "system",
         "content": "你是搜索扩展助手。针对给定词，返回 3 个最相关的衍生搜索词（变体、"
                    "相关话题、口语化叫法），用逗号分隔。只输出词，不要别的。"},
        {"role": "user", "content": word},
    ]
    out = chat(messages, max_tokens=80, temperature=0.6)
    if not out:
        return [word]
    words = [w.strip() for w in out.replace("，", ",").split(",") if w.strip()]
    words = [w for w in words if word in w or w in word or len(w) <= 12][:3]
    return list(dict.fromkeys([word] + words))
