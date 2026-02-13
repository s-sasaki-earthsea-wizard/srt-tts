"""SRTファイルのパース・書き出し機能を提供するモジュール"""

from dataclasses import dataclass
from pathlib import Path

import pysrt


@dataclass
class Subtitle:
    """字幕データを表すクラス"""

    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        """字幕の表示時間（ミリ秒）を返す"""
        return self.end_ms - self.start_ms


def _time_to_ms(time: pysrt.SubRipTime) -> int:
    """pysrtの時間オブジェクトをミリ秒に変換する"""
    return (time.hours * 3600 + time.minutes * 60 + time.seconds) * 1000 + time.milliseconds


def parse_srt(file_path: str | Path) -> list[Subtitle]:
    """
    SRTファイルをパースして字幕リストを返す

    Args:
        file_path: SRTファイルのパス

    Returns:
        字幕データのリスト
    """
    subs = pysrt.open(str(file_path), encoding="utf-8")

    return [
        Subtitle(
            index=sub.index,
            start_ms=_time_to_ms(sub.start),
            end_ms=_time_to_ms(sub.end),
            text=sub.text.replace("\n", " "),
        )
        for sub in subs
    ]


def _ms_to_srt_time(ms: int) -> str:
    """ミリ秒をSRTタイムスタンプ形式（HH:MM:SS,mmm）に変換する"""
    hours = ms // 3_600_000
    ms %= 3_600_000
    minutes = ms // 60_000
    ms %= 60_000
    seconds = ms // 1_000
    millis = ms % 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def write_srt(
    subtitles: list[Subtitle],
    texts: list[str],
    output_path: str | Path,
) -> None:
    """
    字幕データとテキストからSRTファイルを生成する

    Args:
        subtitles: 字幕データのリスト（タイムスタンプ用）
        texts: 出力するテキストのリスト（タグ付き・意訳済みなど）
        output_path: 出力SRTファイルのパス
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    for subtitle, text in zip(subtitles, texts):
        lines.append(str(subtitle.index))
        start = _ms_to_srt_time(subtitle.start_ms)
        end = _ms_to_srt_time(subtitle.end_ms)
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
