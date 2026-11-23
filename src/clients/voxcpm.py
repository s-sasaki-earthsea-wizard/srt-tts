"""Local VoxCPM2 TTS client running on Apple Silicon via MLX (mlx-audio)."""

import os
import re
from pathlib import Path

from pydub import AudioSegment

DEFAULT_MODEL = "mlx-community/VoxCPM2-4bit"
DEFAULT_VOICE_DIR = "voices"
DEFAULT_SEED = 42
DEFAULT_INFERENCE_TIMESTEPS = 10
DEFAULT_CFG_VALUE = 2.0

REFERENCE_AUDIO_STEM = "reference"
REFERENCE_AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac")
REFERENCE_TEXT_NAME = "reference.txt"

# ElevenLabs-style audio tags ([laughs], [softly], ...) are read aloud by VoxCPM.
AUDIO_TAG_PATTERN = re.compile(r"\[[^\]]*\]")
MULTISPACE_PATTERN = re.compile(r"\s{2,}")

# Length of the placeholder written for text that is empty after tag removal.
EMPTY_TEXT_SILENCE_MS = 10


def find_reference_voice(voice_dir: Path, lang: str) -> tuple[Path | None, str | None]:
    """Find the reference audio and transcript for a language.

    Looks in ``voice_dir/<lang>/`` first, then falls back to the base language
    code (e.g. ``zh-CN`` -> ``zh``, ``pt-BR`` -> ``pt``).

    Args:
        voice_dir: Root directory holding per-language reference voices.
        lang: Language code passed via --lang.

    Returns:
        (reference audio path, transcript) where either may be None. The
        transcript is None when reference.txt is missing or empty.
    """
    candidates = [lang]
    base_lang = lang.split("-")[0]
    if base_lang != lang:
        candidates.append(base_lang)

    for name in candidates:
        lang_dir = voice_dir / name
        for ext in REFERENCE_AUDIO_EXTENSIONS:
            audio_path = lang_dir / f"{REFERENCE_AUDIO_STEM}{ext}"
            if audio_path.is_file():
                text_path = lang_dir / REFERENCE_TEXT_NAME
                text = text_path.read_text(encoding="utf-8").strip() if text_path.is_file() else ""
                return audio_path, (text or None)
    return None, None


class VoxCPMClient:
    """VoxCPM2 TTS client (MLX port, runs locally on Apple Silicon).

    Voice selection:
        - reference audio + transcript: transcript-conditioned cloning
          (ref_audio + prompt_audio + prompt_text), the most faithful mode
        - reference audio only: reference cloning (ref_audio)
        - no reference: zero-shot; the voice may differ between entries
    """

    def __init__(
        self,
        lang: str,
        model_id: str | None = None,
        voice_dir: str | Path | None = None,
        seed: int = DEFAULT_SEED,
        inference_timesteps: int = DEFAULT_INFERENCE_TIMESTEPS,
        cfg_value: float = DEFAULT_CFG_VALUE,
    ):
        """
        Args:
            lang: Language code, used only to pick the reference voice.
            model_id: Hugging Face model id. Defaults to $VOXCPM_MODEL or DEFAULT_MODEL.
            voice_dir: Reference voice root. Defaults to $VOXCPM_VOICE_DIR or DEFAULT_VOICE_DIR.
            seed: RNG seed applied before every generation for reproducibility.
            inference_timesteps: Diffusion steps per patch (lower is faster).
            cfg_value: Classifier-free guidance scale.

        Raises:
            RuntimeError: If mlx-audio is not available on this platform.
        """
        # Imported lazily: numpy and mlx are installed only on Apple Silicon macOS.
        try:
            import mlx.core as mx
            import numpy as np
            from mlx_audio.tts import load_model
        except ImportError as e:
            raise RuntimeError(
                "VoxCPM requires mlx-audio, which runs only on Apple Silicon macOS. "
                "Run `uv sync` on an Apple Silicon Mac, or use --tts-provider elevenlabs."
            ) from e

        self._mx = mx
        self._np = np
        self.model_id = model_id or os.getenv("VOXCPM_MODEL", DEFAULT_MODEL)
        self.voice_dir = Path(voice_dir or os.getenv("VOXCPM_VOICE_DIR", DEFAULT_VOICE_DIR))
        self.seed = seed
        self.inference_timesteps = inference_timesteps
        self.cfg_value = cfg_value

        self.reference_audio, self.reference_text = find_reference_voice(self.voice_dir, lang)
        if self.reference_audio is None:
            mode = "zero-shot (no reference voice; the voice may vary between entries)"
        elif self.reference_text is None:
            mode = "reference cloning (no transcript)"
        else:
            mode = "transcript-conditioned cloning"
        print(f"[VoxCPM] Loading {self.model_id}")
        print(f"[VoxCPM] Voice: {self.reference_audio or 'none'} -> {mode}")

        self.model = load_model(self.model_id)
        self.sample_rate = self.model.sample_rate

    def synthesize(self, text: str, output_path: str | Path) -> Path:
        """Synthesize text and write it to output_path.

        Args:
            text: Text to speak. ElevenLabs audio tags are stripped first.
            output_path: Destination file; the suffix selects the format (e.g. .mp3).

        Returns:
            The written file path.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        audio_format = output_path.suffix.lstrip(".") or "mp3"

        plain_text = MULTISPACE_PATTERN.sub(" ", AUDIO_TAG_PATTERN.sub("", text)).strip()
        if not plain_text:
            AudioSegment.silent(duration=EMPTY_TEXT_SILENCE_MS, frame_rate=self.sample_rate).export(
                str(output_path), format=audio_format
            )
            return output_path

        kwargs = {
            "text": plain_text,
            "inference_timesteps": self.inference_timesteps,
            "cfg_value": self.cfg_value,
        }
        if self.reference_audio is not None:
            kwargs["ref_audio"] = str(self.reference_audio)
            if self.reference_text is not None:
                # mlx-audio ignores `ref_text`; the transcript-conditioned mode
                # is ref_audio + prompt_audio + prompt_text.
                kwargs["prompt_audio"] = str(self.reference_audio)
                kwargs["prompt_text"] = self.reference_text

        np = self._np
        self._mx.random.seed(self.seed)
        chunks = [np.asarray(result.audio, dtype=np.float32) for result in self.model.generate(**kwargs)]
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)

        pcm = (np.clip(audio, -1.0, 1.0) * np.iinfo(np.int16).max).astype(np.int16)
        segment = AudioSegment(
            pcm.tobytes(), frame_rate=self.sample_rate, sample_width=2, channels=1
        )
        segment.export(str(output_path), format=audio_format)
        return output_path
