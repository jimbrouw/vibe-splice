"""Per-track audio extraction via FFmpeg.

Each camera/mic source file -> mono 16 kHz float32 numpy array, decoded by
piping s16le PCM out of ffmpeg. No temp files.
"""

import shutil
import subprocess

import numpy as np

SAMPLE_RATE = 16000


def find_ffmpeg() -> str:
    for cand in ("/opt/homebrew/bin/ffmpeg", "ffmpeg", "/usr/local/bin/ffmpeg"):
        if shutil.which(cand):
            return cand
    raise RuntimeError("ffmpeg not found")


def extract_mono(path: str, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Decode any media file's first audio stream to mono float32 in [-1, 1]."""
    proc = subprocess.run(
        [find_ffmpeg(), "-hide_banner", "-loglevel", "error",
         "-i", path, "-map", "0:a:0", "-ac", "1", "-ar", str(sample_rate),
         "-f", "s16le", "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {path}: {proc.stderr.decode(errors='replace')[:500]}")
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
