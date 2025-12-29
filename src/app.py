"""SRTファイルを音声化するメインモジュール"""

import argparse
import json
import sys
import tempfile
import traceback
from pathlib import Path

from dotenv import load_dotenv

from .audio import adjust_audio_speed, combine_audio_segments, get_audio_duration_ms
from .clients import LLMClient, TTSClient
from .parsers import Subtitle, parse_srt
from .processors import AudioTagProcessor


def process_subtitle(
    subtitle: Subtitle,
    tts_client: TTSClient,
    audio_tag_processor: AudioTagProcessor | None,
    temp_dir: Path,
) -> tuple[int, Path, str]:
    """
    1つの字幕を処理して音声ファイルを生成する

    Args:
        subtitle: 字幕データ
        tts_client: TTSクライアント
        audio_tag_processor: オーディオタグプロセッサ（Noneの場合はタグ付けをスキップ）
        temp_dir: 一時ファイル用ディレクトリ

    Returns:
        (開始時間ms, 音声ファイルパス, タグ付きテキスト)のタプル
    """
    text = subtitle.text

    # オーディオタグを付与
    if audio_tag_processor:
        try:
            tagged_text = audio_tag_processor.add_tags(text)
            print(f"    [タグ付与成功]")
            print(f"    元テキスト: {text}")
            print(f"    タグ付き: {tagged_text}")
            text = tagged_text
        except Exception as e:
            print(f"    [タグ付与エラー] {e}")
            traceback.print_exc()

    # 音声を生成
    raw_audio_path = temp_dir / f"raw_{subtitle.index}.mp3"
    tts_client.synthesize(text, raw_audio_path)

    # 音声の長さを確認
    audio_duration = get_audio_duration_ms(raw_audio_path)
    target_duration = subtitle.duration_ms

    if audio_duration > target_duration:
        # 速度調整が必要
        adjusted_path = temp_dir / f"adjusted_{subtitle.index}.mp3"
        adjust_audio_speed(raw_audio_path, target_duration, adjusted_path)
        print(f"    速度調整: {audio_duration}ms -> {target_duration}ms")
        return (subtitle.start_ms, adjusted_path, text)

    return (subtitle.start_ms, raw_audio_path, text)


def save_tagged_json(
    srt_path: Path,
    subtitles: list[Subtitle],
    tagged_texts: list[str],
    output_path: Path,
) -> None:
    """
    オーディオタグ付きテキストをJSONファイルに保存する

    Args:
        srt_path: 入力SRTファイルのパス
        subtitles: 字幕データのリスト
        tagged_texts: タグ付きテキストのリスト
        output_path: 出力JSONファイルのパス
    """
    print(f"[JSON保存開始] {output_path}")

    data = {
        "source": srt_path.name,
        "subtitles": [
            {
                "index": subtitle.index,
                "start_ms": subtitle.start_ms,
                "end_ms": subtitle.end_ms,
                "original_text": subtitle.text,
                "tagged_text": tagged_text,
            }
            for subtitle, tagged_text in zip(subtitles, tagged_texts)
        ],
    }

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[JSON保存] ディレクトリ確認OK: {output_path.parent}")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[JSON保存完了] {output_path}")
        print(f"[JSON内容プレビュー] {len(data['subtitles'])}件の字幕")
    except Exception as e:
        print(f"[JSON保存エラー] {e}")
        traceback.print_exc()


def process_srt_file(srt_path: Path, output_path: Path, use_audio_tags: bool = True) -> None:
    """
    SRTファイルを処理して音声ファイルを生成する

    Args:
        srt_path: 入力SRTファイルのパス
        output_path: 出力音声ファイルのパス
        use_audio_tags: オーディオタグを使用するか
    """
    print(f"処理開始: {srt_path}")
    print(f"出力先: {output_path}")
    print(f"オーディオタグ使用: {use_audio_tags}")

    # SRTをパース
    subtitles = parse_srt(srt_path)
    print(f"字幕数: {len(subtitles)}")

    # クライアントを初期化
    tts_client = TTSClient()
    print("[TTS] クライアント初期化完了")

    audio_tag_processor = None
    if use_audio_tags:
        try:
            llm_client = LLMClient()
            audio_tag_processor = AudioTagProcessor(llm_client)
            print("[LLM] オーディオタグプロセッサ初期化完了")
        except ValueError as e:
            print(f"[LLM] オーディオタグ無効: {e}")
        except Exception as e:
            print(f"[LLM] 初期化エラー: {e}")
            traceback.print_exc()

    # 一時ディレクトリで処理
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        audio_segments: list[tuple[int, Path]] = []
        tagged_texts: list[str] = []

        # 各字幕を処理
        for subtitle in subtitles:
            print(f"処理中: [{subtitle.index}] {subtitle.text[:30]}...")
            start_ms, audio_path, tagged_text = process_subtitle(
                subtitle, tts_client, audio_tag_processor, temp_path
            )
            audio_segments.append((start_ms, audio_path))
            tagged_texts.append(tagged_text)

        # 全ての音声を結合
        print("音声を結合中...")
        combine_audio_segments(audio_segments, output_path)

    # タグ付きJSONを保存
    print(f"[DEBUG] tagged_texts数: {len(tagged_texts)}")
    json_output_path = output_path.with_suffix(".json")
    save_tagged_json(srt_path, subtitles, tagged_texts, json_output_path)

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
    parser.add_argument(
        "--no-tags",
        action="store_true",
        help="オーディオタグの付与をスキップする",
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

    process_srt_file(input_path, output_path, use_audio_tags=not args.no_tags)


if __name__ == "__main__":
    main()
