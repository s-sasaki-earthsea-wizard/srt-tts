"""gTTSによる音声長見積もりクライアントモジュール"""

import re
import tempfile
from pathlib import Path

from gtts import gTTS

from ..audio import get_audio_duration_ms


class GTTSEstimator:
    """gTTSを使用して音声長を見積もるクライアント"""

    # ElevenLabsのオーディオタグを除去するための正規表現
    AUDIO_TAG_PATTERN = re.compile(r"<[^>]+>")

    def __init__(self, estimation_ratio: float = 0.9):
        """
        Args:
            estimation_ratio: gTTS音声長に対する補正係数（デフォルト0.9）
                gTTSの見積もり時間にこの係数を掛けてElevenLabsの時間を推定する
        """
        self.estimation_ratio = estimation_ratio

    def _strip_audio_tags(self, text: str) -> str:
        """
        テキストからオーディオタグを除去する

        Args:
            text: オーディオタグを含むテキスト

        Returns:
            タグが除去されたプレーンテキスト
        """
        return self.AUDIO_TAG_PATTERN.sub("", text).strip()

    def estimate_duration_ms(self, text: str, lang: str = "ja") -> int:
        """
        gTTSでテキストの音声長を見積もる

        Args:
            text: 見積もり対象のテキスト（オーディオタグ含む可）
            lang: 言語コード（デフォルト: ja）

        Returns:
            見積もり音声長（ミリ秒）、補正係数適用済み
        """
        # オーディオタグを除去
        plain_text = self._strip_audio_tags(text)

        if not plain_text:
            return 0

        # 一時ファイルに音声を生成
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = Path(f.name)

        try:
            tts = gTTS(text=plain_text, lang=lang)
            tts.save(str(temp_path))

            # 音声長を取得
            raw_duration = get_audio_duration_ms(temp_path)

            # 補正係数を適用
            estimated_duration = int(raw_duration * self.estimation_ratio)

            return estimated_duration
        finally:
            # 一時ファイルを削除
            if temp_path.exists():
                temp_path.unlink()

    def will_fit_in_duration(self, text: str, available_ms: int, lang: str = "ja") -> bool:
        """
        テキストが指定時間内に収まるかどうかを判定する

        Args:
            text: 判定対象のテキスト
            available_ms: 利用可能な時間（ミリ秒）
            lang: 言語コード

        Returns:
            収まる場合はTrue、収まらない場合はFalse
        """
        estimated = self.estimate_duration_ms(text, lang)
        return estimated <= available_ms
