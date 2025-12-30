"""OpenAI互換LLM APIクライアントモジュール"""

import json
import os
from typing import Any

import requests


class LLMClient:
    """OpenAI互換LLM APIクライアント"""

    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")

        if not self.api_key:
            raise ValueError("LLM_API_KEY環境変数が設定されていません")

    def chat(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        """
        チャットAPIを呼び出す

        Args:
            messages: メッセージのリスト
            json_mode: JSONモードを有効にするか

        Returns:
            アシスタントの応答テキスト
        """
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        response = requests.post(url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]

    def chat_json(self, messages: list[dict[str, str]]) -> dict:
        """
        チャットAPIをJSONモードで呼び出し、パース済みの辞書を返す

        Args:
            messages: メッセージのリスト

        Returns:
            パース済みのJSON辞書
        """
        content = self.chat(messages, json_mode=True)
        return json.loads(content)
