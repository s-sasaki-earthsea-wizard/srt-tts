"""Common interface for TTS clients."""

from pathlib import Path
from typing import Protocol


class TTSClient(Protocol):
    """A TTS engine that renders text to an audio file."""

    def synthesize(self, text: str, output_path: str | Path) -> Path:
        """Synthesize text and write the audio to output_path.

        Args:
            text: Text to speak.
            output_path: Destination audio file. The suffix selects the format.

        Returns:
            The written file path.
        """
        ...
