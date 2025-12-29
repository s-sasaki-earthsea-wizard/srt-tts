"""SRTファイルを音声化するメインモジュール"""

import argparse
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from .audio import adjust_audio_speed, combine_audio_segments, get_audio_duration_ms
from .clients import TTSClient
from .parsers import Subtitle, parse_srt


def process_subtitle(
    subtitle: Subtitle,
    tts_client: TTSClient,
    temp_dir: Path,
) -> tuple[int, Path]:
    """
    1つの字幕を処理して音声ファイルを生成する

    Args:
        subtitle: 字幕データ
        tts_client: TTSクライアント
        temp_dir: 一時ファイル用ディレクトリ

    Returns:
        (開始時間ms, 音声ファイルパス)のタプル
    """
    # 音声を生成
    raw_audio_path = temp_dir / f"raw_{subtitle.index}.mp3"
    tts_client.synthesize(subtitle.text, raw_audio_path)

    # 音声の長さを確認
    audio_duration = get_audio_duration_ms(raw_audio_path)
    target_duration = subtitle.duration_ms

    if audio_duration > target_duration:
        # 速度調整が必要
        adjusted_path = temp_dir / f"adjusted_{subtitle.index}.mp3"
        adjust_audio_speed(raw_audio_path, target_duration, adjusted_path)
        print(f"  [{subtitle.index}] 速度調整: {audio_duration}ms -> {target_duration}ms")
        return (subtitle.start_ms, adjusted_path)

    return (subtitle.start_ms, raw_audio_path)


def process_srt_file(srt_path: Path, output_path: Path) -> None:
    """
    SRTファイルを処理して音声ファイルを生成する

    Args:
        srt_path: 入力SRTファイルのパス
        output_path: 出力音声ファイルのパス
    """
    print(f"処理開始: {srt_path}")

    # SRTをパース
    subtitles = parse_srt(srt_path)
    print(f"字幕数: {len(subtitles)}")

    # TTSクライアントを初期化
    tts_client = TTSClient()

    # 一時ディレクトリで処理
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        audio_segments: list[tuple[int, Path]] = []

        # 各字幕を処理
        for i, subtitle in enumerate(subtitles):
            print(f"処理中: [{subtitle.index}] {subtitle.text[:30]}...")
            start_ms, audio_path = process_subtitle(subtitle, tts_client, temp_path)
            audio_segments.append((start_ms, audio_path))

        # 全ての音声を結合
        print("音声を結合中...")
        combine_audio_segments(audio_segments, output_path)

    print(f"完了: {output_path}")


def main() -> None:
    """メイン関数"""
    load_dotenv()

    parser = argparse.ArgumentParser(description="SRTファイルを音声化する")
    parser.add_argument("input", help="入力SRTファイルのパス")
    parser.add_argument(
        "-o",
        "--output",
        help="出力ファイルのパス（省略時は入力ファイル名.mp3）",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"エラー: ファイルが見つかりません: {input_path}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path("output") / f"{input_path.stem}.mp3"

    process_srt_file(input_path, output_path)


if __name__ == "__main__":
    main()
