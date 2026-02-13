"""短縮テキストの意味一貫性バリデーション機能を提供するモジュール"""

import logging

from ..clients import LLMClient
from ..prompts import load_prompt

logger = logging.getLogger(__name__)

# 整合性チェックの信頼度閾値
CONFIDENCE_THRESHOLD = 0.7


class ConsistencyValidator:
    """LLMを使用して短縮テキストの意味一貫性を検証するバリデーター"""

    def __init__(self, llm_client: LLMClient, debug: bool = False):
        """
        Args:
            llm_client: LLMクライアント
            debug: デバッグモードを有効にするか
        """
        self.llm = llm_client
        self.prompt = load_prompt("shorten_consistency_check_system")
        self.debug = debug

    def check(
        self,
        original_text: str,
        shortened_text: str,
        entry_index: int | None = None,
    ) -> bool:
        """
        短縮テキストが元のテキストの意味を保持しているか検証する

        Args:
            original_text: 元のテキスト
            shortened_text: 短縮されたテキスト
            entry_index: エントリーのインデックス（ログ用）

        Returns:
            整合性がある場合True
        """
        index_str = f"[{entry_index}] " if entry_index is not None else ""

        user_prompt = f"""Please check if the shortened text preserves the essential meaning.

## Original Text
{original_text}

## Shortened Text
{shortened_text}

Evaluate whether the shortened version conveys the same core message."""

        messages = [
            {"role": "system", "content": self.prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self.llm.chat_json(messages)
            is_consistent = response.get("is_consistent", False)
            confidence = response.get("confidence", 0.0)
            issues = response.get("issues", [])

            if self.debug:
                logger.debug(
                    f"{index_str}整合性確認: "
                    f"consistent={is_consistent}, confidence={confidence:.2f}"
                )
                if issues:
                    logger.debug(f"{index_str}問題点: {issues}")

            # 信頼度が閾値以上で整合性ありの場合のみ許可
            if is_consistent and confidence >= CONFIDENCE_THRESHOLD:
                return True

            logger.warning(
                f"{index_str}整合性チェック不合格: "
                f"consistent={is_consistent}, confidence={confidence:.2f}"
            )
            if issues:
                logger.warning(f"{index_str}問題点: {issues}")
            return False

        except Exception as e:
            logger.warning(f"{index_str}整合性確認エラー: {e}")
            # エラー時は安全のため不整合とする
            return False
