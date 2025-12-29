"""字幕処理と音声生成を担当するモジュール"""

import traceback
from pathlib import Path

from ..audio import adjust_audio_speed, get_audio_duration_ms
from ..clients import TTSClient
from ..parsers import Subtitle
from .audio_tag import AudioTagProcessor


class SubtitleProcessor:
    """字幕を処理して音声ファイルを生成するプロセッサ"""

    def __init__(
        self,
        tts_client: TTSClient | None,
        audio_tag_processor: AudioTagProcessor | None,
        speed_threshold: float = 1.0,
        max_shorten_retries: int = 2,
        margin_ms: int = 100,
    ):
        """
        Args:
            tts_client: TTSクライアント（Noneの場合はTTSをスキップ）
            audio_tag_processor: オーディオタグプロセッサ（Noneの場合はタグ付けをスキップ）
            speed_threshold: 速度調整の閾値（これ以下で再意訳）
            max_shorten_retries: 再意訳の最大リトライ回数
            margin_ms: エントリー間の最低マージン（ミリ秒）
        """
        self.tts_client = tts_client
        self.audio_tag_processor = audio_tag_processor
        self.speed_threshold = speed_threshold
        self.max_shorten_retries = max_shorten_retries
        self.margin_ms = margin_ms

    def process(
        self,
        subtitle: Subtitle,
        temp_dir: Path | None,
        prev_texts: list[str] | None = None,
        next_texts: list[str] | None = None,
        prev_entry_end_ms: int | None = None,
        next_entry_start_ms: int | None = None,
    ) -> tuple[int, Path | None, str]:
        """
        1つの字幕を処理して音声ファイルを生成する

        Args:
            subtitle: 字幕データ
            temp_dir: 一時ファイル用ディレクトリ
            prev_texts: 前のエントリーのテキストリスト
            next_texts: 次のエントリーのテキストリスト
            prev_entry_end_ms: 前のエントリーの終了時間（ミリ秒）
            next_entry_start_ms: 次のエントリーの開始時間（ミリ秒）

        Returns:
            (開始時間ms, 音声ファイルパス, タグ付きテキスト)のタプル
        """
        text = subtitle.text

        # オーディオタグを付与
        if self.audio_tag_processor:
            try:
                tagged_text = self.audio_tag_processor.add_tags(
                    text,
                    prev_texts=prev_texts,
                    next_texts=next_texts,
                    entry_index=subtitle.index,
                )
                print(f"    [タグ付与成功]")
                print(f"    元テキスト: {text}")
                print(f"    タグ付き: {tagged_text}")
                text = tagged_text
            except Exception as e:
                print(f"    [タグ付与エラー] {e}")
                traceback.print_exc()

        # TTSクライアントがない場合はスキップ
        if not self.tts_client or not temp_dir:
            return (subtitle.start_ms, None, text)

        # 音声生成とリトライ処理
        return self._generate_audio_with_retry(
            subtitle=subtitle,
            text=text,
            temp_dir=temp_dir,
            prev_texts=prev_texts,
            next_texts=next_texts,
            prev_entry_end_ms=prev_entry_end_ms,
            next_entry_start_ms=next_entry_start_ms,
        )

    def _generate_audio_with_retry(
        self,
        subtitle: Subtitle,
        text: str,
        temp_dir: Path,
        prev_texts: list[str] | None,
        next_texts: list[str] | None,
        prev_entry_end_ms: int | None,
        next_entry_start_ms: int | None,
    ) -> tuple[int, Path | None, str]:
        """
        音声生成とリトライ処理を行う

        Args:
            subtitle: 字幕データ
            text: 処理済みテキスト（タグ付き）
            temp_dir: 一時ファイル用ディレクトリ
            prev_texts: 前のエントリーのテキストリスト
            next_texts: 次のエントリーのテキストリスト
            prev_entry_end_ms: 前のエントリーの終了時間（ミリ秒）
            next_entry_start_ms: 次のエントリーの開始時間（ミリ秒）

        Returns:
            (開始時間ms, 音声ファイルパス, 最終テキスト)のタプル
        """
        # 利用可能な時間枠を計算
        available_start, available_end = self._calculate_available_time_window(
            subtitle, prev_entry_end_ms, next_entry_start_ms
        )
        available_total = available_end - available_start

        for retry in range(self.max_shorten_retries + 1):
            # 音声を生成
            raw_audio_path = temp_dir / f"raw_{subtitle.index}.mp3"
            self.tts_client.synthesize(text, raw_audio_path)

            # 音声の長さを確認
            audio_duration = get_audio_duration_ms(raw_audio_path)

            if audio_duration <= available_total:
                # 速度調整不要、配置位置を決定
                start_ms = self._determine_start_position(
                    subtitle, audio_duration, available_start, available_end
                )
                return (start_ms, raw_audio_path, text)

            # 速度調整が必要
            speed_ratio = available_total / audio_duration

            if speed_ratio >= self.speed_threshold:
                # 閾値内なので速度調整して終了
                return self._adjust_and_return(
                    subtitle, raw_audio_path, available_total, audio_duration,
                    temp_dir, text, available_start
                )

            # 閾値を超えた場合
            if retry == self.max_shorten_retries:
                # 最大リトライ回数到達: 警告を出して速度調整で続行
                print(
                    f"    [警告] 最大リトライ回数到達 "
                    f"(速度比: {speed_ratio:.2f} < 閾値: {self.speed_threshold})"
                )
                return self._adjust_and_return(
                    subtitle, raw_audio_path, available_total, audio_duration,
                    temp_dir, text, available_start
                )

            # 再意訳を依頼
            text = self._shorten_text(
                text=text,
                speed_ratio=speed_ratio,
                retry=retry,
                subtitle=subtitle,
                prev_texts=prev_texts,
                next_texts=next_texts,
            )

            if text is None:
                # エラー時は速度調整で続行
                return self._adjust_and_return(
                    subtitle, raw_audio_path, available_total, audio_duration,
                    temp_dir, text, available_start
                )

        # ここには到達しないはずだが、念のため
        return (available_start, raw_audio_path, text)

    def _calculate_available_time_window(
        self,
        subtitle: Subtitle,
        prev_entry_end_ms: int | None,
        next_entry_start_ms: int | None,
    ) -> tuple[int, int]:
        """
        利用可能な時間枠を計算する

        前後のエントリーとの間にマージンを確保しつつ、
        余裕がある方向に拡張した時間枠を返す。

        Args:
            subtitle: 字幕データ
            prev_entry_end_ms: 前のエントリーの終了時間
            next_entry_start_ms: 次のエントリーの開始時間

        Returns:
            (利用可能な開始位置ms, 利用可能な終了位置ms)
        """
        # 前側の余裕を計算
        if prev_entry_end_ms is not None:
            available_start = prev_entry_end_ms + self.margin_ms
        else:
            # 最初のエントリー: 0から開始可能
            available_start = 0

        # 元のstart_msより前には行かない（ただし前に余裕がある場合は調整可能）
        available_start = min(available_start, subtitle.start_ms)

        # 後側の余裕を計算
        if next_entry_start_ms is not None:
            available_end = next_entry_start_ms - self.margin_ms
        else:
            # 最後のエントリー: 十分な余裕を持たせる
            available_end = subtitle.end_ms + 10000

        return (available_start, available_end)

    def _determine_start_position(
        self,
        subtitle: Subtitle,
        audio_duration: int,
        available_start: int,
        available_end: int,
    ) -> int:
        """
        音声の開始位置を決定する

        余裕がある方向に優先的に配置する。

        Args:
            subtitle: 字幕データ
            audio_duration: 音声の長さ（ミリ秒）
            available_start: 利用可能な開始位置
            available_end: 利用可能な終了位置

        Returns:
            開始位置（ミリ秒）
        """
        # 元のタイムスタンプに収まる場合は元の位置を維持
        if audio_duration <= subtitle.duration_ms:
            return subtitle.start_ms

        # はみ出す量を計算
        overflow = audio_duration - subtitle.duration_ms

        # 前後の余裕を計算
        margin_before = subtitle.start_ms - available_start
        margin_after = available_end - subtitle.end_ms

        if margin_before >= margin_after:
            # 前側に余裕がある: 開始位置を前にずらす
            shift = min(overflow, margin_before)
            return subtitle.start_ms - shift
        else:
            # 後側に余裕がある: 開始位置は維持（後ろにはみ出す）
            return subtitle.start_ms

    def _adjust_and_return(
        self,
        subtitle: Subtitle,
        raw_audio_path: Path,
        target_duration: int,
        audio_duration: int,
        temp_dir: Path,
        text: str,
        start_ms: int | None = None,
    ) -> tuple[int, Path, str]:
        """速度調整して結果を返す"""
        adjusted_path = temp_dir / f"adjusted_{subtitle.index}.mp3"
        adjust_audio_speed(raw_audio_path, target_duration, adjusted_path)
        print(f"    速度調整: {audio_duration}ms -> {target_duration}ms")
        return (start_ms if start_ms is not None else subtitle.start_ms, adjusted_path, text)

    def _shorten_text(
        self,
        text: str,
        speed_ratio: float,
        retry: int,
        subtitle: Subtitle,
        prev_texts: list[str] | None,
        next_texts: list[str] | None,
    ) -> str | None:
        """テキストを短縮する。エラー時はNoneを返す"""
        if not self.audio_tag_processor:
            return None

        # 文字数削減の目標値は速度比の85%
        target_char_ratio = speed_ratio * 0.85
        print(
            f"    [再意訳] 速度比 {speed_ratio:.2f} < 閾値 {self.speed_threshold} "
            f"-> 目標 {target_char_ratio:.0%} に短縮 (リトライ {retry + 1}/{self.max_shorten_retries})"
        )
        print(f"    元テキスト: {text}")

        try:
            shortened_text = self.audio_tag_processor.shorten_text(
                text,
                target_char_ratio,
                prev_texts=prev_texts,
                next_texts=next_texts,
                entry_index=subtitle.index,
            )
            print(f"    短縮後: {shortened_text}")
            return shortened_text
        except Exception as e:
            print(f"    [再意訳エラー] {e}")
            traceback.print_exc()
            return None
