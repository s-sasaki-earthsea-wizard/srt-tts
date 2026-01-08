"""リトライ機能付きLLMクライアントモジュール

JSONパースエラーと言語バリデーション失敗時のリトライを処理する。
"""

import json
import logging
from typing import Any

from .llm import LLMClient
from ..validators import LanguageValidator

logger = logging.getLogger(__name__)


class LLMRetryClient:
    """リトライ機能付きLLMクライアント

    JSONパースエラーと言語バリデーション失敗時に自動リトライを行う。
    """

    # 最大リトライ回数
    MAX_RETRIES = 3

    def __init__(
        self,
        llm_client: LLMClient,
        target_lang: str | None = None,
    ):
        """
        Args:
            llm_client: LLMClientインスタンス
            target_lang: ターゲット言語コード（Noneの場合は言語バリデーション無効）
        """
        self.llm_client = llm_client
        self.target_lang = target_lang

        # 言語バリデーター（ターゲット言語が指定された場合のみ）
        self.language_validator = (
            LanguageValidator(target_lang) if target_lang else None
        )

    def chat_json_with_validation(
        self,
        messages: list[dict[str, str]],
        result_key: str,
        fallback: Any,
        entry_index: int | None = None,
        operation: str = "処理",
    ) -> Any:
        """
        言語バリデーションとJSONエラーリトライ付きでLLMを呼び出す

        Args:
            messages: LLMに送信するメッセージ
            result_key: レスポンスJSONから取得するキー
            fallback: バリデーション/パース失敗時のフォールバック値
            entry_index: エントリーのインデックス（ログ用）
            operation: 操作名（ログ用）

        Returns:
            バリデーション済みの結果値
        """
        index_str = f"[{entry_index}]" if entry_index is not None else ""

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # JSONモードでLLM呼び出し
                result = self.llm_client.chat_json(messages)
                output_value = result.get(result_key, fallback)

                # 言語バリデーターが無効な場合はそのまま返す
                if self.language_validator is None:
                    return output_value

                # 文字列以外は言語バリデーションをスキップ
                if not isinstance(output_value, str):
                    return output_value

                # 言語バリデーション
                if self.language_validator.validate(output_value):
                    return output_value

                # 言語バリデーション失敗
                self._log_validation_failure(
                    index_str, operation, output_value, attempt
                )

            except json.JSONDecodeError as e:
                # JSONパースエラー
                self._log_json_error(index_str, operation, e, attempt)

        # 最大リトライ回数に達した場合
        logger.error(
            f"{index_str} {operation}が{self.MAX_RETRIES}回失敗。"
            f"フォールバック値を使用します。"
        )
        return fallback

    def _log_validation_failure(
        self,
        index_str: str,
        operation: str,
        output_text: str,
        attempt: int,
    ) -> None:
        """言語バリデーション失敗時のログ出力"""
        if attempt < self.MAX_RETRIES:
            detected_lang = self.language_validator.get_detected_language(output_text)
            logger.warning(
                f"{index_str} {operation}結果の言語が不一致 "
                f"(検出: {detected_lang}, 期待: {self.target_lang})。"
                f"リトライ {attempt + 1}/{self.MAX_RETRIES}"
            )

    def _log_json_error(
        self,
        index_str: str,
        operation: str,
        error: json.JSONDecodeError,
        attempt: int,
    ) -> None:
        """JSONパースエラー時のログ出力"""
        if attempt < self.MAX_RETRIES:
            logger.warning(
                f"{index_str} {operation}のJSONパースに失敗: {error}。"
                f"リトライ {attempt + 1}/{self.MAX_RETRIES}"
            )
        else:
            logger.error(
                f"{index_str} {operation}のJSONパースが{self.MAX_RETRIES}回失敗。"
            )
