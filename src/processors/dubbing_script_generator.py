"""吹き替え脚本生成プロセッサ

日本語SRTを読み込み、平文化して翻訳し、吹き替え用SRTを生成する。
gTTSで発話時間を見積もり、タイムスタンプを調整する。
時間枠に収まらない場合は再翻訳を行い、整合性を確認する。
gTTSモードでは音声ファイルも生成する。
"""

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.audio.processor import adjust_audio_speed, combine_audio_segments
from src.clients.gtts import GTTSEstimator
from src.clients.llm import LLMClient
from src.parsers.srt import Subtitle, parse_srt
from src.validators.language import LanguageValidator

logger = logging.getLogger(__name__)


@dataclass
class EstimatedEntry:
    """見積もり結果を含むエントリー"""

    start_ms: int  # 元の開始時刻
    end_ms: int  # 元の終了時刻
    text: str  # 翻訳テキスト
    estimated_duration_ms: int  # gTTSによる見積もり発話時間
    source_text: str = ""  # 元の日本語テキスト（整合性確認用）
    adjusted_start_ms: int | None = None  # 調整後の開始時刻
    adjusted_end_ms: int | None = None  # 調整後の終了時刻
    retranslation_attempts: int = 0  # 再翻訳試行回数

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


def _load_retranslation_prompt() -> str:
    """再翻訳用システムプロンプトを読み込む"""
    prompt_path = Path(__file__).parent.parent / "prompts" / "retranslation_system.md"
    return prompt_path.read_text(encoding="utf-8")


def _load_consistency_check_prompt() -> str:
    """整合性確認用システムプロンプトを読み込む"""
    prompt_path = Path(__file__).parent.parent / "prompts" / "consistency_check_system.md"
    return prompt_path.read_text(encoding="utf-8")


class DubbingScriptGenerator:
    """吹き替え脚本生成プロセッサ"""

    def __init__(
        self,
        margin_ms: int = 100,
        estimation_ratio: float = 1.0,
        retranslation_retries: int = 2,
        gtts_only: bool = False,
        speed_threshold: float = 0.9,
        debug: bool = False,
    ):
        """
        初期化

        Args:
            margin_ms: エントリー間の最低マージン（ミリ秒）
            estimation_ratio: gTTS見積もりの補正係数
            retranslation_retries: 再翻訳のリトライ回数
            gtts_only: gTTSで音声ファイルも生成するか
            speed_threshold: 速度調整の閾値（これ以下の比率なら速度調整）
            debug: デバッグモードを有効にするか
        """
        self.llm = LLMClient()
        self.gtts = GTTSEstimator(estimation_ratio=estimation_ratio)
        self.system_prompt = _load_system_prompt()
        self.retranslation_prompt = _load_retranslation_prompt()
        self.consistency_check_prompt = _load_consistency_check_prompt()
        self.margin_ms = margin_ms
        self.retranslation_retries = retranslation_retries
        self.gtts_only = gtts_only
        self.speed_threshold = speed_threshold
        self.debug = debug
        self._language_validator: LanguageValidator | None = None

        if debug:
            logging.basicConfig(level=logging.DEBUG)

    def generate(
        self,
        input_path: str | Path,
        target_lang: str,
        output_path: str | Path | None = None,
    ) -> Path | tuple[Path, Path]:
        """
        吹き替え脚本を生成する

        Args:
            input_path: 入力SRTファイルのパス
            target_lang: ターゲット言語コード（例: "en", "ru"）
            output_path: 出力SRTファイルのパス（省略時は自動生成）

        Returns:
            gtts_only=False: 出力SRTファイルのパス
            gtts_only=True: (SRTファイルのパス, MP3ファイルのパス)のタプル
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

        # ターゲット言語を保持
        self._target_lang = target_lang
        self._language_validator = LanguageValidator(target_lang)

        # SRTを読み込み
        subtitles = parse_srt(input_path)
        logger.info(f"読み込んだエントリー数: {len(subtitles)}")

        # ソーステキストのマッピングを作成（整合性確認用）
        source_texts = {sub.index: sub.text for sub in subtitles}

        # LLMで翻訳
        translated_entries = self._translate_with_llm(subtitles, target_lang)
        logger.info(f"生成されたエントリー数: {len(translated_entries)}")

        # gTTSで発話時間を見積もり（ソーステキストも渡す）
        estimated_entries = self._estimate_durations(
            translated_entries, target_lang, source_texts
        )
        over_count = sum(1 for e in estimated_entries if e.is_over_duration)
        logger.info(f"時間超過エントリー数: {over_count}/{len(estimated_entries)}")

        # タイムスタンプを調整（再翻訳を含む）
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

        # gTTSモードの場合は音声ファイルも生成
        if self.gtts_only:
            audio_path = self._synthesize_audio(adjusted_entries, target_lang, output_path)
            return (output_path, audio_path)

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
        self,
        entries: list[dict],
        target_lang: str,
        source_texts: dict[int, str] | None = None,
    ) -> list[EstimatedEntry]:
        """
        gTTSで各エントリーの発話時間を見積もる

        Args:
            entries: 翻訳されたエントリーのリスト
            target_lang: ターゲット言語コード
            source_texts: インデックスをキーとするソーステキストの辞書

        Returns:
            見積もり結果を含むエントリーのリスト
        """
        estimated = []
        for i, entry in enumerate(entries):
            duration_ms = self.gtts.estimate_duration_ms(entry["text"], target_lang)
            # ソーステキストを取得（LLMがエントリーを統合/分割している可能性があるので近似）
            source_text = ""
            if source_texts:
                # エントリーのインデックスに対応するソーステキストを探す
                source_text = source_texts.get(i + 1, "")
            estimated_entry = EstimatedEntry(
                start_ms=entry["start_ms"],
                end_ms=entry["end_ms"],
                text=entry["text"],
                estimated_duration_ms=duration_ms,
                source_text=source_text,
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

            # ケース4: 再翻訳を試みる
            adjusted_start = earliest_start_ms if earliest_start_ms < entry.start_ms else entry.start_ms

            # 利用可能な時間枠を計算
            if i + 1 < len(entries):
                max_end_ms = entries[i + 1].start_ms - self.margin_ms
            else:
                max_end_ms = adjusted_start + entry.estimated_duration_ms

            available_duration_ms = max_end_ms - adjusted_start

            # 再翻訳を試みる
            retranslated = self._retranslate_entry(entry, available_duration_ms, i + 1)

            if retranslated:
                # 再翻訳成功
                entry.text = retranslated["text"]
                entry.estimated_duration_ms = retranslated["duration_ms"]
                entry.adjusted_start_ms = adjusted_start
                entry.adjusted_end_ms = adjusted_start + retranslated["duration_ms"]
                if self.debug:
                    logger.debug(
                        f"[{i + 1}] 再翻訳成功: "
                        f"{entry.estimated_duration_ms}ms → {retranslated['duration_ms']}ms"
                    )
            else:
                # 再翻訳失敗、元の時間枠で配置（速度調整で対応）
                entry.adjusted_start_ms = adjusted_start
                entry.adjusted_end_ms = min(
                    adjusted_start + entry.estimated_duration_ms, max_end_ms
                )

                allocated_duration = entry.adjusted_end_ms - adjusted_start
                shortage_ms = entry.estimated_duration_ms - allocated_duration

                logger.warning(
                    f"[{i + 1}] 再翻訳失敗、速度調整が必要: "
                    f"枠{entry.original_duration_ms}ms / 見積もり{entry.estimated_duration_ms}ms / "
                    f"割当{allocated_duration}ms (不足{shortage_ms}ms): "
                    f"{entry.text[:50]}..."
                )

        return entries

    def _retranslate_entry(
        self,
        entry: EstimatedEntry,
        target_duration_ms: int,
        entry_index: int,
    ) -> dict | None:
        """
        エントリーを再翻訳して時間枠に収める

        Args:
            entry: 再翻訳対象のエントリー
            target_duration_ms: 目標の発話時間（ミリ秒）
            entry_index: エントリーのインデックス（ログ用）

        Returns:
            成功時: {"text": str, "duration_ms": int}
            失敗時: None
        """
        if not self._target_lang:
            return None

        original_text = entry.text

        for attempt in range(self.retranslation_retries):
            entry.retranslation_attempts += 1

            # 目標文字数を概算（日本語の場合の目安: 1秒あたり約4-5文字、英語は約2-3単語）
            # gTTSの速度から逆算
            target_chars = int(len(original_text) * target_duration_ms / entry.estimated_duration_ms * 0.95)

            user_prompt = f"""Please shorten the following translation to fit within the time constraint.

## Original Translation
{original_text}

## Time Constraint
- Current estimated duration: {entry.estimated_duration_ms}ms
- Target duration: {target_duration_ms}ms
- Suggested character count: approximately {target_chars} characters or fewer

## Source Text (Japanese, for reference)
{entry.source_text if entry.source_text else "(not available)"}

Please create a shorter version that preserves the core meaning."""

            messages = [
                {"role": "system", "content": self.retranslation_prompt},
                {"role": "user", "content": user_prompt},
            ]

            try:
                response = self.llm.chat_json(messages)
                retranslated_text = response.get("retranslated_text", "")

                if not retranslated_text:
                    logger.warning(f"[{entry_index}] 再翻訳レスポンスが空 (試行{attempt + 1})")
                    continue

                # 言語検証
                if self._language_validator and not self._language_validator.validate(retranslated_text):
                    logger.warning(
                        f"[{entry_index}] 再翻訳の言語が不正 (試行{attempt + 1}): "
                        f"{retranslated_text[:30]}..."
                    )
                    continue

                # gTTSで再見積もり
                new_duration_ms = self.gtts.estimate_duration_ms(
                    retranslated_text, self._target_lang
                )

                # 整合性確認
                if not self._check_consistency(original_text, retranslated_text, entry.source_text, entry_index):
                    logger.warning(
                        f"[{entry_index}] 再翻訳の整合性確認失敗 (試行{attempt + 1})"
                    )
                    continue

                # 時間枠に収まるか確認
                if new_duration_ms <= target_duration_ms:
                    if self.debug:
                        logger.debug(
                            f"[{entry_index}] 再翻訳成功 (試行{attempt + 1}): "
                            f"{entry.estimated_duration_ms}ms → {new_duration_ms}ms"
                        )
                    return {"text": retranslated_text, "duration_ms": new_duration_ms}

                # まだ長すぎる場合は次の試行で更に短くする
                original_text = retranslated_text
                if self.debug:
                    logger.debug(
                        f"[{entry_index}] 再翻訳後もまだ長い (試行{attempt + 1}): "
                        f"{new_duration_ms}ms > {target_duration_ms}ms"
                    )

            except Exception as e:
                logger.warning(f"[{entry_index}] 再翻訳エラー (試行{attempt + 1}): {e}")
                continue

        return None

    def _check_consistency(
        self,
        original_text: str,
        retranslated_text: str,
        source_text: str,
        entry_index: int,
    ) -> bool:
        """
        再翻訳結果と元のテキストの整合性を確認する

        Args:
            original_text: 元の翻訳テキスト
            retranslated_text: 再翻訳されたテキスト
            source_text: 元の日本語テキスト
            entry_index: エントリーのインデックス（ログ用）

        Returns:
            整合性がある場合True
        """
        user_prompt = f"""Please check if the shortened translation preserves the essential meaning.

## Original Translation
{original_text}

## Shortened Translation
{retranslated_text}

## Source Text (Japanese, for reference)
{source_text if source_text else "(not available)"}

Evaluate whether the shortened version conveys the same core message."""

        messages = [
            {"role": "system", "content": self.consistency_check_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self.llm.chat_json(messages)
            is_consistent = response.get("is_consistent", False)
            confidence = response.get("confidence", 0.0)
            issues = response.get("issues", [])

            if self.debug:
                logger.debug(
                    f"[{entry_index}] 整合性確認: "
                    f"consistent={is_consistent}, confidence={confidence:.2f}"
                )
                if issues:
                    logger.debug(f"[{entry_index}] 問題点: {issues}")

            # 信頼度が0.7以上で整合性ありの場合のみ許可
            return is_consistent and confidence >= 0.7

        except Exception as e:
            logger.warning(f"[{entry_index}] 整合性確認エラー: {e}")
            # エラー時は安全のため不整合とする
            return False

    def _synthesize_audio(
        self,
        entries: list[EstimatedEntry],
        target_lang: str,
        srt_path: Path,
    ) -> Path:
        """
        各エントリーの音声を合成し、結合してMP3ファイルを生成する

        Args:
            entries: タイムスタンプ調整済みのエントリーリスト
            target_lang: ターゲット言語コード
            srt_path: 出力SRTファイルのパス（MP3パス決定用）

        Returns:
            生成されたMP3ファイルのパス
        """
        logger.info("音声合成を開始します...")

        # 一時ディレクトリを作成
        temp_dir = Path(tempfile.mkdtemp(prefix="dubbing_"))
        audio_segments: list[tuple[int, Path]] = []

        try:
            for i, entry in enumerate(entries):
                if not entry.text or entry.adjusted_start_ms is None:
                    continue

                # gTTSで音声を生成
                temp_audio_path = temp_dir / f"segment_{i:04d}.mp3"
                _, actual_duration_ms = self.gtts.synthesize(
                    entry.text, temp_audio_path, target_lang
                )

                # 割り当て時間を計算
                allocated_duration_ms = entry.adjusted_end_ms - entry.adjusted_start_ms

                # 速度調整が必要か判定
                if actual_duration_ms > allocated_duration_ms:
                    speed_ratio = allocated_duration_ms / actual_duration_ms
                    if speed_ratio >= self.speed_threshold:
                        # 速度調整で対応
                        adjusted_audio_path = temp_dir / f"adjusted_{i:04d}.mp3"
                        adjust_audio_speed(
                            temp_audio_path, allocated_duration_ms, adjusted_audio_path
                        )
                        audio_segments.append((entry.adjusted_start_ms, adjusted_audio_path))
                        if self.debug:
                            logger.debug(
                                f"[{i + 1}] 速度調整: {actual_duration_ms}ms → "
                                f"{allocated_duration_ms}ms (速度比: {1/speed_ratio:.2f}x)"
                            )
                    else:
                        # 速度調整の閾値を超えている場合は警告
                        logger.warning(
                            f"[{i + 1}] 速度調整閾値超過: "
                            f"必要な速度比 {1/speed_ratio:.2f}x > {1/self.speed_threshold:.2f}x"
                        )
                        # それでも速度調整を適用
                        adjusted_audio_path = temp_dir / f"adjusted_{i:04d}.mp3"
                        adjust_audio_speed(
                            temp_audio_path, allocated_duration_ms, adjusted_audio_path
                        )
                        audio_segments.append((entry.adjusted_start_ms, adjusted_audio_path))
                else:
                    # そのまま使用
                    audio_segments.append((entry.adjusted_start_ms, temp_audio_path))
                    if self.debug:
                        logger.debug(
                            f"[{i + 1}] 音声生成完了: {actual_duration_ms}ms "
                            f"(枠: {allocated_duration_ms}ms)"
                        )

            # 全音声を結合
            output_audio_path = srt_path.with_suffix(".mp3")
            combine_audio_segments(audio_segments, output_audio_path)
            logger.info(f"音声ファイルを出力しました: {output_audio_path}")

            return output_audio_path

        finally:
            # 一時ファイルを削除
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
