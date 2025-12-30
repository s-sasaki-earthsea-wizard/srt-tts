"""SRTファイルのパース機能を提供するモジュール"""

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
