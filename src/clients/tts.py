"""ElevenLabs TTS APIクライアントモジュール"""

import os
from pathlib import Path

import requests


class TTSClient:
    """ElevenLabs TTS APIクライアント"""

    def __init__(self):
        self.api_key = os.getenv("TTS_API_KEY")
        self.base_url = os.getenv("TTS_BASE_URL", "https://api.elevenlabs.io/v1")
        self.model = os.getenv("TTS_MODEL", "eleven_v3")
        self.voice_id = os.getenv("TTS_VOICE_ID")

        if not self.api_key:
            raise ValueError("TTS_API_KEY環境変数が設定されていません")
        if not self.voice_id:
            raise ValueError("TTS_VOICE_ID環境変数が設定されていません")

    def synthesize(self, text: str, output_path: str | Path) -> Path:
        """
        テキストを音声に変換してファイルに保存する

        Args:
            text: 変換するテキスト
            output_path: 出力ファイルパス

        Returns:
            保存されたファイルのパス
        """
        output_path = Path(output_path)
        url = f"{self.base_url.rstrip('/')}/text-to-speech/{self.voice_id}"

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "text": text,
            "model_id": self.model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5,
            },
        }

        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)

        return output_path
