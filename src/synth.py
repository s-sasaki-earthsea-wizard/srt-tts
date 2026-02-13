"""SRTファイルからgTTSで音声を生成するエントリポイント

既存のSRTファイルを読み込み、gTTSで音声を合成してMP3ファイルを生成する。
"""

import argparse
import logging
import shutil
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from .audio.processor import adjust_audio_speed, combine_audio_segments
from .clients.gtts import GTTSEstimator
from .parsers.srt import parse_srt

logger = logging.getLogger(__name__)


def main() -> None:
    """メイン関数"""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="SRTファイルからgTTSで音声を生成する"
    )
    parser.add_argument("input", help="入力SRTファイルのパス")
    parser.add_argument(
        "--lang",
        type=str,
        required=True,
        help="言語コード（例: en, ru, es, ko, zh-CN）",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="出力MP3ファイルのパス（省略時は自動生成）",
    )
    parser.add_argument(
        "--speed-threshold",
        type=float,
        default=0.9,
        help="速度調整の閾値（デフォルト: 0.9）",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="デバッグモードを有効にする",
    )

    args = parser.parse_args()

    # デバッグモードでロギングを設定
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
        )

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"エラー: ファイルが見つかりません: {input_path}", file=sys.stderr)
        sys.exit(1)

    # 出力パスを決定
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_suffix(".mp3")

    # SRTを読み込み
    subtitles = parse_srt(input_path)
    logger.info(f"読み込んだエントリー数: {len(subtitles)}")

    # 音声を合成
    synthesize_from_srt(
        subtitles=subtitles,
        lang=args.lang,
        output_path=output_path,
        speed_threshold=args.speed_threshold,
        debug=args.debug,
    )

    print(f"音声ファイルを生成しました: {output_path}")


def synthesize_from_srt(
    subtitles: list,
    lang: str,
    output_path: Path,
    speed_threshold: float = 0.9,
    debug: bool = False,
) -> Path:
    """
    SRTのエントリーリストから音声を合成する

    Args:
        subtitles: SRTエントリーのリスト
        lang: 言語コード
        output_path: 出力MP3ファイルのパス
        speed_threshold: 速度調整の閾値
        debug: デバッグモード

    Returns:
        生成されたMP3ファイルのパス
    """
    gtts = GTTSEstimator(estimation_ratio=1.0)
    temp_dir = Path(tempfile.mkdtemp(prefix="synth_"))
    audio_segments: list[tuple[int, Path]] = []

    try:
        for i, entry in enumerate(subtitles):
            if not entry.text:
                continue

            # gTTSで音声を生成
            temp_audio_path = temp_dir / f"segment_{i:04d}.mp3"
            _, actual_duration_ms = gtts.synthesize(
                entry.text, temp_audio_path, lang
            )

            # 割り当て時間を計算
            allocated_duration_ms = entry.end_ms - entry.start_ms

            # 速度調整が必要か判定
            if actual_duration_ms > allocated_duration_ms:
                speed_ratio = allocated_duration_ms / actual_duration_ms
                if speed_ratio >= speed_threshold:
                    # 速度調整で対応
                    adjusted_audio_path = temp_dir / f"adjusted_{i:04d}.mp3"
                    adjust_audio_speed(
                        temp_audio_path, allocated_duration_ms, adjusted_audio_path
                    )
                    audio_segments.append((entry.start_ms, adjusted_audio_path))
                    if debug:
                        logger.debug(
                            f"[{i + 1}] 速度調整: {actual_duration_ms}ms → "
                            f"{allocated_duration_ms}ms (速度比: {1/speed_ratio:.2f}x)"
                        )
                else:
                    # 速度調整の閾値を超えている場合は警告
                    logger.warning(
                        f"[{i + 1}] 速度調整閾値超過: "
                        f"必要な速度比 {1/speed_ratio:.2f}x > {1/speed_threshold:.2f}x"
                    )
                    # それでも速度調整を適用
                    adjusted_audio_path = temp_dir / f"adjusted_{i:04d}.mp3"
                    adjust_audio_speed(
                        temp_audio_path, allocated_duration_ms, adjusted_audio_path
                    )
                    audio_segments.append((entry.start_ms, adjusted_audio_path))
            else:
                # そのまま使用
                audio_segments.append((entry.start_ms, temp_audio_path))
                if debug:
                    logger.debug(
                        f"[{i + 1}] 音声生成完了: {actual_duration_ms}ms "
                        f"(枠: {allocated_duration_ms}ms)"
                    )

        # 全音声を結合
        combine_audio_segments(audio_segments, output_path)
        logger.info(f"音声ファイルを出力しました: {output_path}")

        return output_path

    finally:
        # 一時ファイルを削除
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
