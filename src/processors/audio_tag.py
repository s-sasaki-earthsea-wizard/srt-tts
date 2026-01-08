"""オーディオタグ付与機能を提供するモジュール"""

import logging

from ..clients import LLMClient
from ..prompts import load_prompt
from ..validators import LanguageValidator

logger = logging.getLogger(__name__)


class AudioTagProcessor:
    """LLMを使用してテキストにオーディオタグを付与するプロセッサ"""

    # 言語バリデーション失敗時のリトライ回数
    MAX_VALIDATION_RETRIES = 3

    def __init__(
        self, llm_client: LLMClient, debug: bool = False, target_lang: str | None = None
    ):
        self.llm_client = llm_client
        self.debug = debug
        self.target_lang = target_lang
        self.system_prompt = load_prompt("audio_tag_system")
        self.shorten_prompt = load_prompt("shorten_text_system")

        # 言語バリデーター（ターゲット言語が指定された場合のみ）
        self.language_validator = (
            LanguageValidator(target_lang) if target_lang else None
        )

    def add_tags(
        self,
        text: str,
        prev_texts: list[str] | None = None,
        next_texts: list[str] | None = None,
        entry_index: int | None = None,
    ) -> str:
        """
        テキストにオーディオタグを付与する

        Args:
            text: 元のテキスト（タグ付与対象）
            prev_texts: 前のエントリーのテキストリスト（最大2つ）
            next_texts: 次のエントリーのテキストリスト（最大2つ）
            entry_index: エントリーのインデックス（ログ用）

        Returns:
            オーディオタグが付与されたテキスト
        """
        # コンテキストを構築
        context_parts = []

        if prev_texts:
            context_parts.append("## Previous entries (for context only):")
            for i, prev_text in enumerate(prev_texts, 1):
                context_parts.append(f"[-{len(prev_texts) - i + 1}] {prev_text}")
            context_parts.append("")

        context_parts.append("## TARGET text (add tags to this):")
        context_parts.append(text)
        context_parts.append("")

        if next_texts:
            context_parts.append("## Next entries (for context only):")
            for i, next_text in enumerate(next_texts, 1):
                context_parts.append(f"[+{i}] {next_text}")

        user_content = "\n".join(context_parts)

        # デバッグログ: LLMに送信するコンテキスト
        if self.debug:
            index_str = f"[{entry_index}]" if entry_index is not None else ""
            logger.debug(f"=== タグ付与リクエスト {index_str} ===")
            logger.debug(f"対象テキスト: {text}")
            if prev_texts:
                logger.debug(f"前のコンテキスト: {prev_texts}")
            if next_texts:
                logger.debug(f"次のコンテキスト: {next_texts}")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]

        # 言語バリデーション付きでLLM呼び出し
        tagged_text = self._call_llm_with_validation(
            messages=messages,
            result_key="tagged_text",
            fallback=text,
            entry_index=entry_index,
            operation="タグ付与",
        )

        # デバッグログ: LLMからの応答
        if self.debug:
            logger.debug(f"タグ付き結果: {tagged_text}")
            logger.debug("=" * 50)

        return tagged_text

    def shorten_text(
        self,
        text: str,
        target_ratio: float,
        prev_texts: list[str] | None = None,
        next_texts: list[str] | None = None,
        entry_index: int | None = None,
    ) -> str:
        """
        テキストを指定比率に短縮し、オーディオタグも付与する

        Args:
            text: 元のテキスト（短縮対象）
            target_ratio: 目標短縮率（0.7 = 70%に短縮）
            prev_texts: 前のエントリーのテキストリスト（最大2つ）
            next_texts: 次のエントリーのテキストリスト（最大2つ）
            entry_index: エントリーのインデックス（ログ用）

        Returns:
            短縮されたテキスト（オーディオタグ付き）
        """
        # コンテキストを構築
        context_parts = []

        context_parts.append(f"## Target Ratio: {target_ratio:.0%}")
        context_parts.append(
            f"(Shorten to approximately {target_ratio:.0%} of original length)"
        )
        context_parts.append("")

        if prev_texts:
            context_parts.append("## Previous entries (for context only):")
            for i, prev_text in enumerate(prev_texts, 1):
                context_parts.append(f"[-{len(prev_texts) - i + 1}] {prev_text}")
            context_parts.append("")

        context_parts.append("## TARGET text (shorten this):")
        context_parts.append(text)
        context_parts.append("")

        if next_texts:
            context_parts.append("## Next entries (for context only):")
            for i, next_text in enumerate(next_texts, 1):
                context_parts.append(f"[+{i}] {next_text}")

        user_content = "\n".join(context_parts)

        # デバッグログ: LLMに送信するコンテキスト
        if self.debug:
            index_str = f"[{entry_index}]" if entry_index is not None else ""
            logger.debug(f"=== 短縮リクエスト {index_str} ===")
            logger.debug(f"対象テキスト: {text}")
            logger.debug(f"目標比率: {target_ratio:.0%}")
            if prev_texts:
                logger.debug(f"前のコンテキスト: {prev_texts}")
            if next_texts:
                logger.debug(f"次のコンテキスト: {next_texts}")

        messages = [
            {"role": "system", "content": self.shorten_prompt},
            {"role": "user", "content": user_content},
        ]

        # 言語バリデーション付きでLLM呼び出し
        shortened_text = self._call_llm_with_validation(
            messages=messages,
            result_key="shortened_text",
            fallback=text,
            entry_index=entry_index,
            operation="短縮",
        )

        # デバッグログ: LLMからの応答
        if self.debug:
            logger.debug(f"短縮結果: {shortened_text}")
            logger.debug("=" * 50)

        return shortened_text

    def _call_llm_with_validation(
        self,
        messages: list[dict],
        result_key: str,
        fallback: str,
        entry_index: int | None = None,
        operation: str = "処理",
    ) -> str:
        """
        言語バリデーション付きでLLMを呼び出す

        Args:
            messages: LLMに送信するメッセージ
            result_key: レスポンスJSONから取得するキー
            fallback: バリデーション失敗時のフォールバック値
            entry_index: エントリーのインデックス（ログ用）
            operation: 操作名（ログ用）

        Returns:
            バリデーション済みのテキスト
        """
        index_str = f"[{entry_index}]" if entry_index is not None else ""

        for attempt in range(self.MAX_VALIDATION_RETRIES + 1):
            result = self.llm_client.chat_json(messages)
            output_text = result.get(result_key, fallback)

            # 言語バリデーターが無効な場合はそのまま返す
            if self.language_validator is None:
                return output_text

            # 言語バリデーション
            if self.language_validator.validate(output_text):
                return output_text

            # バリデーション失敗
            if attempt < self.MAX_VALIDATION_RETRIES:
                detected_lang = self.language_validator.get_detected_language(
                    output_text
                )
                logger.warning(
                    f"{index_str} {operation}結果の言語が不一致 "
                    f"(検出: {detected_lang}, 期待: {self.target_lang})。"
                    f"リトライ {attempt + 1}/{self.MAX_VALIDATION_RETRIES}"
                )
            else:
                # 最大リトライ回数に達した場合
                detected_lang = self.language_validator.get_detected_language(
                    output_text
                )
                logger.error(
                    f"{index_str} {operation}結果の言語バリデーションが"
                    f"{self.MAX_VALIDATION_RETRIES}回失敗。"
                    f"フォールバック値を使用します。"
                )
                return fallback

        return fallback
