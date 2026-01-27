"""吹き替え脚本生成プロセッサ

日本語SRTを読み込み、平文化して翻訳し、吹き替え用SRTを生成する。
gTTSで発話時間を見積もり、タイムスタンプを調整する。
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from src.clients.gtts import GTTSEstimator
from src.clients.llm import LLMClient
from src.parsers.srt import Subtitle, parse_srt

logger = logging.getLogger(__name__)


@dataclass
class EstimatedEntry:
    """見積もり結果を含むエントリー"""

    start_ms: int  # 元の開始時刻
    end_ms: int  # 元の終了時刻
    text: str  # 翻訳テキスト
    estimated_duration_ms: int  # gTTSによる見積もり発話時間
    adjusted_start_ms: int | None = None  # 調整後の開始時刻
    adjusted_end_ms: int | None = None  # 調整後の終了時刻

    @property
    def original_duration_ms(self) -> int:
        """元の時間枠"""
        return self.end_ms - self.start_ms

    @property
    def is_over_duration(self) -> bool:
        """元の時間枠を超過しているか"""
        return self.estimated_duration_ms > self.original_duration_ms


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

    def __init__(
        self,
        margin_ms: int = 100,
        estimation_ratio: float = 1.0,
        debug: bool = False,
    ):
        """
        初期化

        Args:
            margin_ms: エントリー間の最低マージン（ミリ秒）
            estimation_ratio: gTTS見積もりの補正係数
            debug: デバッグモードを有効にするか
        """
        self.llm = LLMClient()
        self.gtts = GTTSEstimator(estimation_ratio=estimation_ratio)
        self.system_prompt = _load_system_prompt()
        self.margin_ms = margin_ms
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

        # gTTSで発話時間を見積もり
        estimated_entries = self._estimate_durations(translated_entries, target_lang)
        over_count = sum(1 for e in estimated_entries if e.is_over_duration)
        logger.info(f"時間超過エントリー数: {over_count}/{len(estimated_entries)}")

        # タイムスタンプを調整
        adjusted_entries = self._adjust_timestamps(estimated_entries)

        # SRTファイルを生成
        final_entries = [
            {
                "start_ms": e.adjusted_start_ms,
                "end_ms": e.adjusted_end_ms,
                "text": e.text,
            }
            for e in adjusted_entries
        ]
        srt_content = _create_srt_content(final_entries)
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

    def _estimate_durations(
        self, entries: list[dict], target_lang: str
    ) -> list[EstimatedEntry]:
        """
        gTTSで各エントリーの発話時間を見積もる

        Args:
            entries: 翻訳されたエントリーのリスト
            target_lang: ターゲット言語コード

        Returns:
            見積もり結果を含むエントリーのリスト
        """
        estimated = []
        for i, entry in enumerate(entries):
            duration_ms = self.gtts.estimate_duration_ms(entry["text"], target_lang)
            estimated_entry = EstimatedEntry(
                start_ms=entry["start_ms"],
                end_ms=entry["end_ms"],
                text=entry["text"],
                estimated_duration_ms=duration_ms,
            )
            if self.debug:
                status = "超過" if estimated_entry.is_over_duration else "OK"
                logger.debug(
                    f"[{i + 1}] {estimated_entry.original_duration_ms}ms枠 / "
                    f"見積もり{duration_ms}ms [{status}]: {entry['text'][:30]}..."
                )
            estimated.append(estimated_entry)
        return estimated

    def _adjust_timestamps(
        self, entries: list[EstimatedEntry]
    ) -> list[EstimatedEntry]:
        """
        タイムスタンプを調整する

        調整ロジック:
        1. 時間枠内に収まる → そのまま
        2. 超過 → 前の隙間を使う（前エントリー終了 + margin_ms から開始）
        3. それでも超過 → 次のエントリーが元の時間枠に収まるなら、次の開始まで使える
        4. それでも超過 → 警告を出して元の時間枠で配置（将来的に再翻訳へ）

        Args:
            entries: 見積もり結果を含むエントリーのリスト

        Returns:
            タイムスタンプ調整後のエントリーのリスト
        """
        if not entries:
            return entries

        for i, entry in enumerate(entries):
            # 前のエントリーの終了時刻を取得
            if i == 0:
                prev_end_ms = 0
            else:
                prev_end_ms = entries[i - 1].adjusted_end_ms or entries[i - 1].end_ms

            # 使える最早開始時刻（前のエントリー終了 + マージン）
            earliest_start_ms = prev_end_ms + self.margin_ms if i > 0 else entry.start_ms

            # 元の開始時刻と比較して、早い方は使えない
            available_start_ms = max(earliest_start_ms, 0)
            # ただし元の開始より前に開始できる場合は前にずらせる
            if earliest_start_ms < entry.start_ms:
                available_start_ms = earliest_start_ms

            # デフォルトの終了時刻
            default_end_ms = entry.end_ms

            # 必要な終了時刻（開始 + 見積もり発話時間）
            needed_end_ms = available_start_ms + entry.estimated_duration_ms

            # ケース1: 元の時間枠内に収まる
            if entry.estimated_duration_ms <= entry.original_duration_ms:
                entry.adjusted_start_ms = entry.start_ms
                entry.adjusted_end_ms = entry.start_ms + entry.estimated_duration_ms
                if self.debug:
                    logger.debug(f"[{i + 1}] 時間枠内に収まる")
                continue

            # ケース2: 前の隙間を使って収まるか
            gap_before = entry.start_ms - earliest_start_ms
            if gap_before > 0:
                # 前にずらして収まるか確認
                if earliest_start_ms + entry.estimated_duration_ms <= entry.end_ms:
                    entry.adjusted_start_ms = earliest_start_ms
                    entry.adjusted_end_ms = earliest_start_ms + entry.estimated_duration_ms
                    if self.debug:
                        logger.debug(
                            f"[{i + 1}] 前の隙間を使用: {gap_before}ms前にずらす"
                        )
                    continue

            # ケース3: 次のエントリーの時間枠を確認
            if i + 1 < len(entries):
                next_entry = entries[i + 1]
                # 次のエントリーが元の時間枠に収まるなら、次の開始まで使える
                if next_entry.estimated_duration_ms <= next_entry.original_duration_ms:
                    # 次の開始時刻 - マージン まで使える
                    max_end_ms = next_entry.start_ms - self.margin_ms
                    adjusted_start = max(earliest_start_ms, entry.start_ms - gap_before) if gap_before > 0 else entry.start_ms
                    # できるだけ前にずらす
                    adjusted_start = earliest_start_ms if earliest_start_ms < entry.start_ms else entry.start_ms
                    needed_end = adjusted_start + entry.estimated_duration_ms

                    if needed_end <= max_end_ms:
                        entry.adjusted_start_ms = adjusted_start
                        entry.adjusted_end_ms = needed_end
                        if self.debug:
                            logger.debug(
                                f"[{i + 1}] 次の字幕の開始まで使用: "
                                f"{entry.start_ms}ms → {adjusted_start}ms開始, "
                                f"{entry.end_ms}ms → {needed_end}ms終了"
                            )
                        continue

            # ケース4: どうしても収まらない場合は警告
            # 次のエントリーと重ならないよう、終了時刻を制限する
            adjusted_start = earliest_start_ms if earliest_start_ms < entry.start_ms else entry.start_ms
            needed_end = adjusted_start + entry.estimated_duration_ms

            # 次のエントリーがある場合は、その開始時刻 - margin_ms を終了時刻の上限とする
            if i + 1 < len(entries):
                max_end_ms = entries[i + 1].start_ms - self.margin_ms
                adjusted_end = min(needed_end, max_end_ms)
            else:
                adjusted_end = needed_end

            entry.adjusted_start_ms = adjusted_start
            entry.adjusted_end_ms = adjusted_end

            # 実際に必要な時間と割り当てられた時間の差を計算
            allocated_duration = adjusted_end - adjusted_start
            shortage_ms = entry.estimated_duration_ms - allocated_duration

            logger.warning(
                f"[{i + 1}] 時間枠に収まりません: "
                f"枠{entry.original_duration_ms}ms / 見積もり{entry.estimated_duration_ms}ms / "
                f"割当{allocated_duration}ms (不足{shortage_ms}ms, 将来的に再翻訳が必要): "
                f"{entry.text[:50]}..."
            )

        return entries
