"""音声処理機能を提供するモジュール"""

from pathlib import Path

from pydub import AudioSegment


def get_audio_duration_ms(audio_path: str | Path) -> int:
    """音声ファイルの長さをミリ秒で取得する"""
    audio = AudioSegment.from_file(str(audio_path))
    return len(audio)


def adjust_audio_speed(audio_path: str | Path, target_duration_ms: int, output_path: str | Path) -> Path:
    """
    音声の速度を調整して指定時間に収める

    Args:
        audio_path: 入力音声ファイルのパス
        target_duration_ms: 目標の長さ（ミリ秒）
        output_path: 出力ファイルのパス

    Returns:
        出力ファイルのパス
    """
    audio = AudioSegment.from_file(str(audio_path))
    current_duration = len(audio)
    output_path = Path(output_path)

    if current_duration <= target_duration_ms:
        # 既に目標時間内なのでそのままコピー
        audio.export(str(output_path), format="mp3")
        return output_path

    # 速度調整が必要
    speed_ratio = current_duration / target_duration_ms

    # pydubでは直接速度変更できないため、frame_rateを変更して実現
    # 速度を上げる = frame_rateを上げてから元のframe_rateでエクスポート
    new_frame_rate = int(audio.frame_rate * speed_ratio)
    adjusted = audio._spawn(audio.raw_data, overrides={"frame_rate": new_frame_rate})
    adjusted = adjusted.set_frame_rate(audio.frame_rate)

    adjusted.export(str(output_path), format="mp3")
    return output_path


def create_silence(duration_ms: int) -> AudioSegment:
    """指定した長さの無音を生成する"""
    return AudioSegment.silent(duration=duration_ms)


def combine_audio_segments(
    audio_files: list[tuple[int, str | Path]],
    output_path: str | Path,
) -> Path:
    """
    複数の音声ファイルをタイムスタンプに合わせて結合する

    Args:
        audio_files: (開始時間ms, ファイルパス)のリスト
        output_path: 出力ファイルのパス

    Returns:
        出力ファイルのパス
    """
    output_path = Path(output_path)

    if not audio_files:
        raise ValueError("結合する音声ファイルがありません")

    # 時間順にソート
    audio_files = sorted(audio_files, key=lambda x: x[0])

    combined = AudioSegment.empty()
    current_position = 0

    for start_ms, file_path in audio_files:
        # 現在位置から開始時間までの無音を追加
        if start_ms > current_position:
            silence_duration = start_ms - current_position
            combined += create_silence(silence_duration)
            current_position = start_ms

        # 音声を追加
        audio = AudioSegment.from_file(str(file_path))
        combined += audio
        current_position += len(audio)

    # MP3として出力
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(output_path), format="mp3", bitrate="192k")

    return output_path
