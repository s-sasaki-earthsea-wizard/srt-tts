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
from .parsers import Subtitle, parse_srt, write_srt
from .processors import AudioTagProcessor, SubtitleProcessor
from .validators import ConsistencyValidator

logger = logging.getLogger(__name__)

# 前後何エントリーをコンテキストとして使用するか
CONTEXT_WINDOW = 2


def save_tagged_json(
    srt_path: Path,
    subtitles: list[Subtitle],
    tagged_texts: list[str],
    output_path: Path,
    durations_ms: list[int] | None = None,
) -> None:
    """
    オーディオタグ付きテキストをJSONファイルに保存する

    Args:
        srt_path: 入力SRTファイルのパス
        subtitles: 字幕データのリスト
        tagged_texts: タグ付きテキストのリスト
        output_path: 出力JSONファイルのパス
        durations_ms: 音声長のリスト（ミリ秒）、Noneの場合は出力しない
    """
    print(f"[JSON保存開始] {output_path}")

    subtitle_data = []
    for i, (subtitle, tagged_text) in enumerate(zip(subtitles, tagged_texts)):
        entry = {
            "index": subtitle.index,
            "start_ms": subtitle.start_ms,
            "end_ms": subtitle.end_ms,
            "available_ms": subtitle.end_ms - subtitle.start_ms,
            "original_text": subtitle.text,
            "tagged_text": tagged_text,
        }
        if durations_ms is not None:
            entry["duration_ms"] = durations_ms[i]
            entry["overflow_ms"] = max(0, durations_ms[i] - entry["available_ms"])
        subtitle_data.append(entry)

    data = {
        "source": srt_path.name,
        "subtitles": subtitle_data,
    }

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[JSON保存] ディレクトリ確認OK: {output_path.parent}")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[JSON保存完了] {output_path}")
        print(f"[JSON内容プレビュー] {len(data['subtitles'])}件の字幕")

        # 時間超過の警告を表示
        if durations_ms is not None:
            overflow_count = sum(1 for entry in subtitle_data if entry.get("overflow_ms", 0) > 0)
            if overflow_count > 0:
                print(f"[警告] {overflow_count}件の字幕が時間枠を超過しています")
    except Exception as e:
        print(f"[JSON保存エラー] {e}")
        traceback.print_exc()


def process_srt_file(
    srt_path: Path,
    output_path: Path,
    use_audio_tags: bool = True,
    json_only: bool = False,
    gtts_only: bool = False,
    debug: bool = False,
    speed_threshold: float = 1.0,
    gtts_shorten_retries: int = 8,
    el_shorten_retries: int = 2,
    margin_ms: int = 100,
    estimation_ratio: float | None = 0.9,
    lang: str = "ja",
    shorten_ratio: float = 0.95,
    consistency_check: bool = True,
) -> None:
    """
    SRTファイルを処理して音声ファイルを生成する

    Args:
        srt_path: 入力SRTファイルのパス
        output_path: 出力音声ファイルのパス
        use_audio_tags: オーディオタグを使用するか
        json_only: TTSをスキップしてJSONのみ出力するか
        gtts_only: gTTSのみで音声生成（ElevenLabsを使用しない）
        debug: デバッグモードを有効にするか（詳細ログ出力）
        speed_threshold: 速度調整の閾値（これ以下で再意訳）
        gtts_shorten_retries: gTTS事前見積もりでの再意訳の最大リトライ回数
        el_shorten_retries: ElevenLabs生成後の再意訳の最大リトライ回数
        margin_ms: エントリー間の最低マージン（ミリ秒）
        estimation_ratio: gTTS事前見積もりの補正係数（Noneで無効化）
        lang: gTTSの言語コード（デフォルト: ja）
        shorten_ratio: 文字数削減の目標係数（デフォルト: 0.95）
        consistency_check: 短縮テキストの意味一貫性チェックを有効にするか
    """
    print(f"処理開始: {srt_path}")
    print(f"出力先: {output_path}")
    print(f"オーディオタグ使用: {use_audio_tags}")
    print(f"JSONのみ: {json_only}")
    print(f"gTTSのみ: {gtts_only}")
    print(f"デバッグモード: {debug}")
    print(f"速度調整閾値: {speed_threshold}")
    print(f"gTTS短縮リトライ回数: {gtts_shorten_retries}"
          f", ElevenLabs短縮リトライ回数: {el_shorten_retries}")
    print(f"エントリー間マージン: {margin_ms}ms")
    print(f"gTTS事前見積もり: {f'有効 (補正係数: {estimation_ratio})' if estimation_ratio else '無効'}")
    print(f"gTTS言語: {lang}")
    print(f"文字数削減係数: {shorten_ratio}")
    print(f"意味一貫性チェック: {'有効' if consistency_check else '無効'}")

    # SRTをパース
    subtitles = parse_srt(srt_path)
    print(f"字幕数: {len(subtitles)}")

    # TTSクライアントを初期化（json_onlyまたはgtts_onlyの場合はスキップ）
    tts_client = None
    if not json_only and not gtts_only:
        tts_client = TTSClient()
        print("[TTS] クライアント初期化完了")

    # オーディオタグプロセッサと意味一貫性バリデーターを初期化
    audio_tag_processor = None
    consistency_validator = None
    if use_audio_tags:
        try:
            llm_client = LLMClient()
            audio_tag_processor = AudioTagProcessor(
                llm_client, debug=debug, target_lang=lang
            )
            print(f"[LLM] オーディオタグプロセッサ初期化完了（言語バリデーション: {lang}）")

            if consistency_check:
                consistency_validator = ConsistencyValidator(
                    llm_client, debug=debug
                )
                print("[LLM] 意味一貫性バリデーター初期化完了")
        except ValueError as e:
            print(f"[LLM] オーディオタグ無効: {e}")
        except Exception as e:
            print(f"[LLM] 初期化エラー: {e}")
            traceback.print_exc()

    # gTTSクライアントを初期化（gtts_onlyまたは事前見積もり用）
    gtts_estimator = None
    if gtts_only or (estimation_ratio is not None and not json_only):
        ratio = estimation_ratio if estimation_ratio is not None else 1.0
        gtts_estimator = GTTSEstimator(estimation_ratio=ratio)
        if gtts_only:
            print("[gTTS] gTTSのみモードで初期化完了")
        else:
            print(f"[gTTS] 事前見積もりクライアント初期化完了 (補正係数: {ratio})")

    # 字幕プロセッサを初期化
    subtitle_processor = SubtitleProcessor(
        tts_client=tts_client,
        audio_tag_processor=audio_tag_processor,
        speed_threshold=speed_threshold,
        gtts_shorten_retries=gtts_shorten_retries,
        el_shorten_retries=el_shorten_retries,
        margin_ms=margin_ms,
        gtts_estimator=gtts_estimator,
        lang=lang,
        shorten_ratio=shorten_ratio,
        consistency_validator=consistency_validator,
    )

    # 処理
    audio_segments: list[tuple[int, Path]] = []
    tagged_texts: list[str] = []
    durations_ms: list[int] = []

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

    elif gtts_only:
        # gTTSのみモード：ElevenLabsを使わずgTTSで音声生成
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            for i, subtitle in enumerate(subtitles):
                print(f"処理中: [{subtitle.index}] {subtitle.text[:30]}...")
                prev_texts = [s.text for s in subtitles[max(0, i - CONTEXT_WINDOW) : i]]
                next_texts = [s.text for s in subtitles[i + 1 : i + 1 + CONTEXT_WINDOW]]
                prev_entry_end_ms = subtitles[i - 1].end_ms if i > 0 else None
                next_entry_start_ms = subtitles[i + 1].start_ms if i < len(subtitles) - 1 else None

                # オーディオタグを付与
                text = subtitle.text
                if audio_tag_processor:
                    try:
                        tagged_text = audio_tag_processor.add_tags(
                            text,
                            prev_texts=prev_texts if prev_texts else None,
                            next_texts=next_texts if next_texts else None,
                            entry_index=subtitle.index,
                        )
                        print(f"    [タグ付与成功]")
                        text = tagged_text
                    except Exception as e:
                        print(f"    [タグ付与エラー] {e}")

                # 時間枠を計算して事前短縮（前後エントリーとのバッファを考慮）
                available_start, available_end = subtitle_processor._calculate_available_time_window(
                    subtitle, prev_entry_end_ms, next_entry_start_ms
                )
                available_total = available_end - available_start
                text, _ = subtitle_processor._pre_shorten_with_gtts(
                    text=text,
                    available_total=available_total,
                    subtitle=subtitle,
                    prev_texts=prev_texts if prev_texts else None,
                    next_texts=next_texts if next_texts else None,
                )

                tagged_texts.append(text)

                # gTTSで音声を生成
                audio_path = temp_path / f"gtts_{subtitle.index}.mp3"
                _, duration_ms = gtts_estimator.synthesize(text, audio_path, lang=lang)
                durations_ms.append(duration_ms)
                audio_segments.append((subtitle.start_ms, audio_path))

                print(f"    [gTTS生成] {duration_ms}ms")

                # 時間超過の警告を記録
                if duration_ms > available_total:
                    subtitle_processor.warnings.append({
                        "index": subtitle.index,
                        "type": "time_overflow",
                        "available_ms": available_total,
                        "duration_ms": duration_ms,
                        "speed_ratio": round(available_total / duration_ms, 3) if duration_ms > 0 else 0,
                        "text": text,
                    })

            # 全ての音声を結合
            print("音声を結合中...")
            combine_audio_segments(audio_segments, output_path)

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
    save_tagged_json(
        srt_path,
        subtitles,
        tagged_texts,
        json_output_path,
        durations_ms=durations_ms if durations_ms else None,
    )

    # タグ付きSRTを保存
    tagged_srt_path = output_path.with_suffix(".tagged.srt")
    write_srt(subtitles, tagged_texts, tagged_srt_path)
    print(f"[タグ付きSRT保存] {tagged_srt_path}")

    # 警告JSONを保存（警告がある場合のみ）
    if subtitle_processor.warnings:
        warnings_path = output_path.with_suffix(".warnings.json")
        warnings_data = {
            "source": srt_path.name,
            "warnings": subtitle_processor.warnings,
        }
        warnings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(warnings_path, "w", encoding="utf-8") as f:
            json.dump(warnings_data, f, ensure_ascii=False, indent=2)
        print(f"[警告JSON保存] {warnings_path} ({len(subtitle_processor.warnings)}件)")

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
        default=0.9,
        help="速度調整の閾値（デフォルト: 0.9）。これ以下で再意訳を試行",
    )
    parser.add_argument(
        "--gtts-shorten-retries",
        type=int,
        default=4,
        help="gTTS事前見積もりでの再意訳リトライ回数（デフォルト: 4）",
    )
    parser.add_argument(
        "--el-shorten-retries",
        type=int,
        default=2,
        help="ElevenLabs生成後の再意訳リトライ回数（デフォルト: 2）",
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
        default=1.0,
        help="gTTS事前見積もりの補正係数（デフォルト: 1.0）。0以下で無効化",
    )
    parser.add_argument(
        "--gtts-only",
        action="store_true",
        help="gTTSのみで音声生成（ElevenLabsを使用しない）",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="ja",
        help="gTTSの言語コード（デフォルト: ja）。例: en, ja, ko, zh-CN",
    )
    parser.add_argument(
        "--shorten-ratio",
        type=float,
        default=0.95,
        help="文字数削減の目標係数（デフォルト: 0.95）。速度比にこの係数を掛けた値が目標",
    )
    parser.add_argument(
        "--no-consistency-check",
        action="store_true",
        help="短縮テキストの意味一貫性チェックを無効にする",
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
        gtts_only=args.gtts_only,
        debug=args.debug,
        speed_threshold=args.speed_threshold,
        gtts_shorten_retries=args.gtts_shorten_retries,
        el_shorten_retries=args.el_shorten_retries,
        margin_ms=args.margin_ms,
        estimation_ratio=estimation_ratio,
        lang=args.lang,
        shorten_ratio=args.shorten_ratio,
        consistency_check=not args.no_consistency_check,
    )


if __name__ == "__main__":
    main()
