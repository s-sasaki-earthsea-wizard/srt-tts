"""SRTファイルを音声化するメインモジュール"""

import argparse
import json
import logging
import sys
import tempfile
import traceback
from pathlib import Path

from dotenv import load_dotenv

from .audio import adjust_audio_speed, combine_audio_segments, get_audio_duration_ms
from .clients import LLMClient, TTSClient
from .parsers import Subtitle, parse_srt
from .processors import AudioTagProcessor

logger = logging.getLogger(__name__)

# 前後何エントリーをコンテキストとして使用するか
CONTEXT_WINDOW = 2


def process_subtitle(
    subtitle: Subtitle,
    tts_client: TTSClient | None,
    audio_tag_processor: AudioTagProcessor | None,
    temp_dir: Path | None,
    prev_texts: list[str] | None = None,
    next_texts: list[str] | None = None,
) -> tuple[int, Path | None, str]:
    """
    1つの字幕を処理して音声ファイルを生成する

    Args:
        subtitle: 字幕データ
        tts_client: TTSクライアント（Noneの場合はTTSをスキップ）
        audio_tag_processor: オーディオタグプロセッサ（Noneの場合はタグ付けをスキップ）
        temp_dir: 一時ファイル用ディレクトリ
        prev_texts: 前のエントリーのテキストリスト
        next_texts: 次のエントリーのテキストリスト

    Returns:
        (開始時間ms, 音声ファイルパス, タグ付きテキスト)のタプル
    """
    text = subtitle.text

    # オーディオタグを付与
    if audio_tag_processor:
        try:
            tagged_text = audio_tag_processor.add_tags(
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
    if not tts_client or not temp_dir:
        return (subtitle.start_ms, None, text)

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


def process_srt_file(
    srt_path: Path,
    output_path: Path,
    use_audio_tags: bool = True,
    json_only: bool = False,
    debug: bool = False,
) -> None:
    """
    SRTファイルを処理して音声ファイルを生成する

    Args:
        srt_path: 入力SRTファイルのパス
        output_path: 出力音声ファイルのパス
        use_audio_tags: オーディオタグを使用するか
        json_only: TTSをスキップしてJSONのみ出力するか
        debug: デバッグモードを有効にするか（詳細ログ出力）
    """
    print(f"処理開始: {srt_path}")
    print(f"出力先: {output_path}")
    print(f"オーディオタグ使用: {use_audio_tags}")
    print(f"JSONのみ: {json_only}")
    print(f"デバッグモード: {debug}")

    # SRTをパース
    subtitles = parse_srt(srt_path)
    print(f"字幕数: {len(subtitles)}")

    # TTSクライアントを初期化（json_onlyの場合はスキップ）
    tts_client = None
    if not json_only:
        tts_client = TTSClient()
        print("[TTS] クライアント初期化完了")

    # オーディオタグプロセッサを初期化
    audio_tag_processor = None
    if use_audio_tags:
        try:
            llm_client = LLMClient()
            audio_tag_processor = AudioTagProcessor(llm_client, debug=debug)
            print("[LLM] オーディオタグプロセッサ初期化完了")
        except ValueError as e:
            print(f"[LLM] オーディオタグ無効: {e}")
        except Exception as e:
            print(f"[LLM] 初期化エラー: {e}")
            traceback.print_exc()

    # 処理
    audio_segments: list[tuple[int, Path]] = []
    tagged_texts: list[str] = []

    if json_only:
        # JSONのみモード：一時ディレクトリ不要
        for i, subtitle in enumerate(subtitles):
            print(f"処理中: [{subtitle.index}] {subtitle.text[:30]}...")
            prev_texts = [s.text for s in subtitles[max(0, i - CONTEXT_WINDOW) : i]]
            next_texts = [s.text for s in subtitles[i + 1 : i + 1 + CONTEXT_WINDOW]]

            _, _, tagged_text = process_subtitle(
                subtitle,
                None,
                audio_tag_processor,
                None,
                prev_texts=prev_texts if prev_texts else None,
                next_texts=next_texts if next_texts else None,
            )
            tagged_texts.append(tagged_text)
    else:
        # 通常モード：一時ディレクトリで処理
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            for i, subtitle in enumerate(subtitles):
                print(f"処理中: [{subtitle.index}] {subtitle.text[:30]}...")
                prev_texts = [s.text for s in subtitles[max(0, i - CONTEXT_WINDOW) : i]]
                next_texts = [s.text for s in subtitles[i + 1 : i + 1 + CONTEXT_WINDOW]]

                start_ms, audio_path, tagged_text = process_subtitle(
                    subtitle,
                    tts_client,
                    audio_tag_processor,
                    temp_path,
                    prev_texts=prev_texts if prev_texts else None,
                    next_texts=next_texts if next_texts else None,
                )
                if audio_path:
                    audio_segments.append((start_ms, audio_path))
                tagged_texts.append(tagged_text)

            # 全ての音声を結合
            print("音声を結合中...")
            combine_audio_segments(audio_segments, output_path)

    # タグ付きJSONを保存
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
        help="出力ファイルのパス（省略時は入力ファイル名.mp3/.json）",
    )
    parser.add_argument(
        "--no-tags",
        action="store_true",
        help="オーディオタグの付与をスキップする",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="TTSをスキップしてオーディオタグ付きJSONのみを出力する",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="デバッグモードを有効にする（LLMコンテキストと応答を詳細出力）",
    )

    args = parser.parse_args()

    # デバッグモードでロギングを設定
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"エラー: ファイルが見つかりません: {input_path}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        suffix = ".json" if args.json_only else ".mp3"
        output_path = Path("output") / f"{input_path.stem}{suffix}"

    process_srt_file(
        input_path,
        output_path,
        use_audio_tags=not args.no_tags,
        json_only=args.json_only,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()
