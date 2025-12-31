"""SRTファイルを音声化するメインモジュール"""

import argparse
import json
import logging
import sys
import tempfile
import traceback
from pathlib import Path

from dotenv import load_dotenv

from .audio import combine_audio_segments
from .clients import GTTSEstimator, LLMClient, TTSClient
from .parsers import Subtitle, parse_srt
from .processors import AudioTagProcessor, SubtitleProcessor

logger = logging.getLogger(__name__)

# 前後何エントリーをコンテキストとして使用するか
CONTEXT_WINDOW = 2


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
    speed_threshold: float = 1.0,
    max_shorten_retries: int = 2,
    margin_ms: int = 100,
    estimation_ratio: float | None = 0.9,
) -> None:
    """
    SRTファイルを処理して音声ファイルを生成する

    Args:
        srt_path: 入力SRTファイルのパス
        output_path: 出力音声ファイルのパス
        use_audio_tags: オーディオタグを使用するか
        json_only: TTSをスキップしてJSONのみ出力するか
        debug: デバッグモードを有効にするか（詳細ログ出力）
        speed_threshold: 速度調整の閾値（これ以下で再意訳）
        max_shorten_retries: 再意訳の最大リトライ回数
        margin_ms: エントリー間の最低マージン（ミリ秒）
        estimation_ratio: gTTS事前見積もりの補正係数（Noneで無効化）
    """
    print(f"処理開始: {srt_path}")
    print(f"出力先: {output_path}")
    print(f"オーディオタグ使用: {use_audio_tags}")
    print(f"JSONのみ: {json_only}")
    print(f"デバッグモード: {debug}")
    print(f"速度調整閾値: {speed_threshold}")
    print(f"最大リトライ回数: {max_shorten_retries}")
    print(f"エントリー間マージン: {margin_ms}ms")
    print(f"gTTS事前見積もり: {f'有効 (補正係数: {estimation_ratio})' if estimation_ratio else '無効'}")

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

    # gTTS事前見積もりクライアントを初期化
    gtts_estimator = None
    if estimation_ratio is not None and not json_only:
        gtts_estimator = GTTSEstimator(estimation_ratio=estimation_ratio)
        print(f"[gTTS] 事前見積もりクライアント初期化完了 (補正係数: {estimation_ratio})")

    # 字幕プロセッサを初期化
    subtitle_processor = SubtitleProcessor(
        tts_client=tts_client,
        audio_tag_processor=audio_tag_processor,
        speed_threshold=speed_threshold,
        max_shorten_retries=max_shorten_retries,
        margin_ms=margin_ms,
        gtts_estimator=gtts_estimator,
    )

    # 処理
    audio_segments: list[tuple[int, Path]] = []
    tagged_texts: list[str] = []

    if json_only:
        # JSONのみモード：一時ディレクトリ不要
        for i, subtitle in enumerate(subtitles):
            print(f"処理中: [{subtitle.index}] {subtitle.text[:30]}...")
            prev_texts = [s.text for s in subtitles[max(0, i - CONTEXT_WINDOW) : i]]
            next_texts = [s.text for s in subtitles[i + 1 : i + 1 + CONTEXT_WINDOW]]
            prev_entry_end_ms = subtitles[i - 1].end_ms if i > 0 else None
            next_entry_start_ms = subtitles[i + 1].start_ms if i < len(subtitles) - 1 else None

            _, _, tagged_text = subtitle_processor.process(
                subtitle,
                temp_dir=None,
                prev_texts=prev_texts if prev_texts else None,
                next_texts=next_texts if next_texts else None,
                prev_entry_end_ms=prev_entry_end_ms,
                next_entry_start_ms=next_entry_start_ms,
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
                prev_entry_end_ms = subtitles[i - 1].end_ms if i > 0 else None
                next_entry_start_ms = subtitles[i + 1].start_ms if i < len(subtitles) - 1 else None

                start_ms, audio_path, tagged_text = subtitle_processor.process(
                    subtitle,
                    temp_dir=temp_path,
                    prev_texts=prev_texts if prev_texts else None,
                    next_texts=next_texts if next_texts else None,
                    prev_entry_end_ms=prev_entry_end_ms,
                    next_entry_start_ms=next_entry_start_ms,
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
    parser.add_argument(
        "--speed-threshold",
        type=float,
        default=1.0,
        help="速度調整の閾値（デフォルト: 1.0）。これ以下で再意訳を試行",
    )
    parser.add_argument(
        "--max-shorten-retries",
        type=int,
        default=2,
        help="再意訳の最大リトライ回数（デフォルト: 2）",
    )
    parser.add_argument(
        "--margin-ms",
        type=int,
        default=100,
        help="エントリー間の最低マージン（ミリ秒、デフォルト: 100）",
    )
    parser.add_argument(
        "--estimation-ratio",
        type=float,
        default=0.9,
        help="gTTS事前見積もりの補正係数（デフォルト: 0.9）。0以下で無効化",
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

    # estimation_ratioが0以下の場合は無効化
    estimation_ratio = args.estimation_ratio if args.estimation_ratio > 0 else None

    process_srt_file(
        input_path,
        output_path,
        use_audio_tags=not args.no_tags,
        json_only=args.json_only,
        debug=args.debug,
        speed_threshold=args.speed_threshold,
        max_shorten_retries=args.max_shorten_retries,
        margin_ms=args.margin_ms,
        estimation_ratio=estimation_ratio,
    )


if __name__ == "__main__":
    main()
