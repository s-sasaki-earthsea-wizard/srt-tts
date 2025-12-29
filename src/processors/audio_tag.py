"""オーディオタグ付与機能を提供するモジュール"""

from ..clients import LLMClient

SYSTEM_PROMPT = """You are an expert at adding audio expression tags to text for text-to-speech synthesis.

Your task is to enhance the given text by adding appropriate audio tags that make the speech more expressive and natural.

## Available Audio Tags

### Emotional expressions
- [laughs] - General laughter
- [chuckles] - Soft, quiet laughter
- [giggles] - Light, playful laughter
- [sighs] - Expressing relief, tiredness, or disappointment
- [gasps] - Surprise or shock
- [excitedly] - Excited tone
- [sadly] - Sad tone
- [whispers] - Quiet, secretive speech
- [shouts] - Loud, emphatic speech

### Pauses and breathing
- [pause] - Brief pause for emphasis
- [long pause] - Longer pause for dramatic effect
- [deep breath] - Taking a breath before speaking

### Voice qualities
- [softly] - Gentle, quiet voice
- [dramatically] - Theatrical emphasis
- [sarcastically] - Ironic tone
- [nervously] - Anxious, uncertain voice

## Guidelines

1. Add tags sparingly - don't overuse them
2. Place tags where they would naturally occur in speech
3. Match the emotional context of the content
4. Keep the original text intact, only add tags
5. For educational or informational content, use minimal tags
6. For narrative or storytelling content, use more expressive tags

## Output Format

Return a JSON object with this structure:
{
  "tagged_text": "The text with [audio tags] inserted appropriately"
}
"""


class AudioTagProcessor:
    """LLMを使用してテキストにオーディオタグを付与するプロセッサ"""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def add_tags(self, text: str) -> str:
        """
        テキストにオーディオタグを付与する

        Args:
            text: 元のテキスト

        Returns:
            オーディオタグが付与されたテキスト
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Add audio tags to the following text:\n\n{text}"},
        ]

        result = self.llm_client.chat_json(messages)
        return result.get("tagged_text", text)
