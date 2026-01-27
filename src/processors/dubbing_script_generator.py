"""吹き替え脚本生成プロセッサ

日本語SRTを読み込み、平文化して翻訳し、吹き替え用SRTを生成する。
"""

import json
import logging
from pathlib import Path

from src.clients.llm import LLMClient
from src.parsers.srt import Subtitle, parse_srt

logger = logging.getLogger(__name__)


def _load_system_prompt() -> str:
    """吹き替え用システムプロンプトを読み込む"""
    prompt_path = Path(__file__).parent.parent / "prompts" / "dubbing_system.md"
    return prompt_path.read_text(encoding="utf-8")


def _format_entries_for_prompt(subtitles: list[Subtitle]) -> str:
    """字幕エントリーをプロンプト用にフォーマットする"""
    lines = []
    for sub in subtitles:
        lines.append(f"{sub.index}. {sub.start_ms}ms --> {sub.end_ms}ms: {sub.text}")
    return "\n".join(lines)


def _ms_to_srt_time(ms: int) -> str:
    """ミリ秒をSRT形式の時間文字列に変換する"""
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    milliseconds = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _create_srt_content(entries: list[dict]) -> str:
    """エントリーリストからSRTファイルの内容を生成する"""
    lines = []
    for i, entry in enumerate(entries, 1):
        start_time = _ms_to_srt_time(entry["start_ms"])
        end_time = _ms_to_srt_time(entry["end_ms"])
        lines.append(str(i))
        lines.append(f"{start_time} --> {end_time}")
        lines.append(entry["text"])
        lines.append("")
    return "\n".join(lines)


class DubbingScriptGenerator:
    """吹き替え脚本生成プロセッサ"""

    def __init__(self, debug: bool = False):
        """
        初期化

        Args:
            debug: デバッグモードを有効にするか
        """
        self.llm = LLMClient()
        self.system_prompt = _load_system_prompt()
        self.debug = debug

        if debug:
            logging.basicConfig(level=logging.DEBUG)

    def generate(
        self,
        input_path: str | Path,
        target_lang: str,
        output_path: str | Path | None = None,
    ) -> Path:
        """
        吹き替え脚本を生成する

        Args:
            input_path: 入力SRTファイルのパス
            target_lang: ターゲット言語コード（例: "en", "ru"）
            output_path: 出力SRTファイルのパス（省略時は自動生成）

        Returns:
            出力ファイルのパス
        """
        input_path = Path(input_path)

        # 出力パスを決定
        if output_path is None:
            # 入力ファイル名から出力ファイル名を生成
            stem = input_path.stem
            # -jp や .ja などのサフィックスを除去して言語コードを追加
            if stem.endswith("-jp") or stem.endswith("-ja"):
                stem = stem[:-3]
            elif stem.endswith(".jp") or stem.endswith(".ja"):
                stem = stem[:-3]
            output_path = input_path.parent / f"{stem}-{target_lang}.srt"
        else:
            output_path = Path(output_path)

        logger.info(f"入力ファイル: {input_path}")
        logger.info(f"ターゲット言語: {target_lang}")
        logger.info(f"出力ファイル: {output_path}")

        # SRTを読み込み
        subtitles = parse_srt(input_path)
        logger.info(f"読み込んだエントリー数: {len(subtitles)}")

        # LLMで翻訳
        translated_entries = self._translate_with_llm(subtitles, target_lang)
        logger.info(f"生成されたエントリー数: {len(translated_entries)}")

        # SRTファイルを生成
        srt_content = _create_srt_content(translated_entries)
        output_path.write_text(srt_content, encoding="utf-8")
        logger.info(f"SRTファイルを出力しました: {output_path}")

        return output_path

    def _translate_with_llm(
        self, subtitles: list[Subtitle], target_lang: str
    ) -> list[dict]:
        """
        LLMを使用して字幕を翻訳する

        Args:
            subtitles: 字幕リスト
            target_lang: ターゲット言語コード

        Returns:
            翻訳されたエントリーのリスト
        """
        # 字幕をフォーマット
        formatted_entries = _format_entries_for_prompt(subtitles)

        # ユーザープロンプトを構築
        user_prompt = f"""Please translate the following Japanese subtitle entries into {target_lang}.

## Subtitle Entries

{formatted_entries}

## Target Language
{target_lang}

Please return the translated entries as a JSON object with the structure specified in the system prompt."""

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        if self.debug:
            logger.debug(f"ユーザープロンプト:\n{user_prompt}")

        # LLMを呼び出し
        response = self.llm.chat_json(messages)

        if self.debug:
            logger.debug(f"LLMレスポンス:\n{json.dumps(response, ensure_ascii=False, indent=2)}")

        return response.get("entries", [])
