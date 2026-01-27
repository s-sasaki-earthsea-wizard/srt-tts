"""吹き替え脚本生成のエントリポイント

日本語SRTを読み込み、指定言語の吹き替え用SRTを生成する。
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from .processors.dubbing_script_generator import DubbingScriptGenerator


def main() -> None:
    """メイン関数"""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="日本語SRTから吹き替え用SRTを生成する"
    )
    parser.add_argument("input", help="入力SRTファイルのパス")
    parser.add_argument(
        "--lang",
        type=str,
        required=True,
        help="ターゲット言語コード（例: en, ru, es, ko, zh-CN）",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="出力SRTファイルのパス（省略時は自動生成）",
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
        help="gTTS見積もりの補正係数（デフォルト: 1.0）",
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

    # 吹き替え脚本生成
    generator = DubbingScriptGenerator(
        margin_ms=args.margin_ms,
        estimation_ratio=args.estimation_ratio,
        debug=args.debug,
    )
    output_path = generator.generate(
        input_path=input_path,
        target_lang=args.lang,
        output_path=args.output,
    )

    print(f"吹き替え脚本を生成しました: {output_path}")


if __name__ == "__main__":
    main()
