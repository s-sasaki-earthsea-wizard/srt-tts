"""言語検出とバリデーション機能を提供するモジュール"""

import re
import logging
from functools import lru_cache

from lingua import Language, LanguageDetectorBuilder

logger = logging.getLogger(__name__)

# gTTS言語コードからlingua Languageへのマッピング
# 現在対応している言語のみ（必要に応じて追加）
LANG_CODE_MAP: dict[str, Language] = {
    "ja": Language.JAPANESE,
    "en": Language.ENGLISH,
    "ko": Language.KOREAN,
    "zh-CN": Language.CHINESE,
    "zh-TW": Language.CHINESE,
    "zh": Language.CHINESE,
    "ru": Language.RUSSIAN,
    "es": Language.SPANISH,
}


class LanguageValidator:
    """言語バリデーションを行うクラス"""

    # 短文時の最小文字数（これ以下はバリデーションをスキップ）
    MIN_TEXT_LENGTH = 10

    def __init__(self, target_lang: str, confidence_threshold: float = 0.5):
        """
        Args:
            target_lang: 期待する言語コード（例: "ja", "en", "ko"）
            confidence_threshold: 言語検出の信頼度閾値（デフォルト: 0.5）
        """
        self.target_lang = target_lang
        self.target_language = LANG_CODE_MAP.get(target_lang)
        self.confidence_threshold = confidence_threshold
        self._detector = self._build_detector()

        if self.target_language is None:
            logger.warning(
                f"未対応の言語コード: {target_lang}。言語バリデーションは無効化されます。"
            )

    @lru_cache(maxsize=1)
    def _build_detector(self):
        """言語検出器を構築（キャッシュ）"""
        return (
            LanguageDetectorBuilder.from_all_languages()
            .with_preloaded_language_models()
            .build()
        )

    def _strip_audio_tags(self, text: str) -> str:
        """オーディオタグを除去してテキストのみを抽出"""
        return re.sub(r"\[.*?\]", "", text).strip()

    def validate(self, tagged_text: str) -> bool:
        """
        タグ付きテキストの言語がターゲット言語と一致するか検証

        Args:
            tagged_text: オーディオタグ付きテキスト

        Returns:
            True: 言語が一致、または検証不可（短文など）
            False: 言語が不一致
        """
        # ターゲット言語が未対応の場合はスキップ
        if self.target_language is None:
            return True

        # オーディオタグを除去
        clean_text = self._strip_audio_tags(tagged_text)

        # 短すぎるテキストはスキップ（検出精度が低いため）
        if len(clean_text) < self.MIN_TEXT_LENGTH:
            return True

        try:
            # 言語を検出
            detected = self._detector.detect_language_of(clean_text)

            if detected is None:
                logger.debug(f"言語検出失敗: {clean_text[:50]}...")
                return True  # 検出失敗時はスキップ

            # 信頼度を取得
            confidence_values = self._detector.compute_language_confidence_values(
                clean_text
            )
            confidence = next(
                (cv.value for cv in confidence_values if cv.language == detected),
                0.0,
            )

            # 信頼度が低い場合はスキップ
            if confidence < self.confidence_threshold:
                logger.debug(
                    f"信頼度が低いためスキップ: {detected.name} ({confidence:.2f})"
                )
                return True

            # 言語が一致するかチェック
            is_match = detected == self.target_language

            if not is_match:
                logger.warning(
                    f"[言語不一致] 期待: {self.target_language.name}, "
                    f"検出: {detected.name} ({confidence:.2f})"
                )
                logger.warning(f"  テキスト: {clean_text[:100]}...")

            return is_match

        except Exception as e:
            logger.warning(f"言語検出エラー: {e}")
            return True  # エラー時はスキップ

    def get_detected_language(self, tagged_text: str) -> str | None:
        """
        テキストの言語を検出して返す（デバッグ用）

        Args:
            tagged_text: オーディオタグ付きテキスト

        Returns:
            検出された言語名、または None
        """
        clean_text = self._strip_audio_tags(tagged_text)

        if len(clean_text) < self.MIN_TEXT_LENGTH:
            return None

        try:
            detected = self._detector.detect_language_of(clean_text)
            return detected.name if detected else None
        except Exception:
            return None
