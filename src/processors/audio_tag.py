"""オーディオタグ付与機能を提供するモジュール"""

from ..clients import LLMClient

SYSTEM_PROMPT = """You are an expert at adding audio expression tags to text for text-to-speech synthesis.

Your task is to enhance the TARGET text by adding appropriate audio tags that make the speech more expressive and natural. You will be given context (previous and next entries) to help you understand the flow and emotional tone.

## Audio Tag Format

Tags are enclosed in square brackets and placed inline with the text. Choose tags that best fit the emotional context - you are not limited to specific tags. Use your judgment to select the most appropriate expressions.

### Example tags (not exhaustive):
- Emotional: [laughs], [chuckles], [sighs], [gasps], [excitedly], [sadly], [whispers], [shouts]
- Voice quality: [softly], [dramatically], [sarcastically], [nervously], [cheerfully], [thoughtfully]
- Any other contextually appropriate expression

## Guidelines

1. Add tags sparingly - don't overuse them
2. Place tags where they would naturally occur in speech
3. Match the emotional context of the content
4. Keep the original text intact, only add tags
5. For educational or informational content, use minimal tags
6. For narrative or storytelling content, use more expressive tags
7. Consider the flow from previous entries and into next entries
8. ONLY add tags to the TARGET text, not to the context
9. DO NOT use pause-related tags like [pause], [long pause], [deep breath] - timing is controlled separately
10. DO NOT place tags at the end of the text - they must come before or within the speech they modify

## Output Format

Return a JSON object with this structure:
{
  "tagged_text": "The TARGET text with [audio tags] inserted appropriately"
}
"""


class AudioTagProcessor:
    """LLMを使用してテキストにオーディオタグを付与するプロセッサ"""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def add_tags(
        self,
        text: str,
        prev_texts: list[str] | None = None,
        next_texts: list[str] | None = None,
    ) -> str:
        """
        テキストにオーディオタグを付与する

        Args:
            text: 元のテキスト（タグ付与対象）
            prev_texts: 前のエントリーのテキストリスト（最大2つ）
            next_texts: 次のエントリーのテキストリスト（最大2つ）

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

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        result = self.llm_client.chat_json(messages)
        return result.get("tagged_text", text)
