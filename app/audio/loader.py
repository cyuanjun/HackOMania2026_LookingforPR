"""Audio file loading and normalization."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import subprocess
import wave

import numpy as np

from app.config import AppConfig, DEFAULT_CONFIG


def _load_with_soundfile(path: Path) -> tuple[np.ndarray, int, int]:
    import soundfile as sf

    info = sf.info(str(path))
    audio, sample_rate = sf.read(str(path), always_2d=True, dtype="float32")
    audio = audio.T
    channels = int(info.channels)
    return audio, int(sample_rate), channels


def _load_with_librosa(path: Path) -> tuple[np.ndarray, int, int]:
    import librosa

    audio, sample_rate = librosa.load(str(path), sr=None, mono=False)
    channels = 1 if getattr(audio, "ndim", 1) == 1 else int(audio.shape[0])
    return np.asarray(audio, dtype=np.float32), int(sample_rate), channels


def _load_with_wave(path: Path) -> tuple[np.ndarray, int, int]:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        raw_frames = wav_file.readframes(frame_count)

    if sample_width == 1:
        dtype = np.uint8
        audio = np.frombuffer(raw_frames, dtype=dtype).astype(np.float32)
        audio = (audio - 128.0) / 128.0
    elif sample_width == 2:
        dtype = np.int16
        audio = np.frombuffer(raw_frames, dtype=dtype).astype(np.float32) / 32768.0
    elif sample_width == 4:
        dtype = np.int32
        audio = np.frombuffer(raw_frames, dtype=dtype).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    if channels > 1:
        audio = audio.reshape(-1, channels).T
    return np.asarray(audio, dtype=np.float32), int(sample_rate), int(channels)


def _load_with_ffmpeg(path: Path) -> tuple[np.ndarray, int, int]:
    """Decode compressed formats through ffmpeg when Python decoders are unavailable."""

    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, check=True)
    audio = np.frombuffer(result.stdout, dtype=np.float32)
    if audio.size == 0:
        raise ValueError(f"ffmpeg produced no audio for {path}")
    return audio, 16_000, 1


def _resample_linear(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr or audio.size == 0:
        return audio.astype(np.float32)

    duration = len(audio) / orig_sr
    old_times = np.linspace(0.0, duration, num=len(audio), endpoint=False)
    new_length = max(1, int(round(duration * target_sr)))
    new_times = np.linspace(0.0, duration, num=new_length, endpoint=False)
    return np.interp(new_times, old_times, audio).astype(np.float32)


def load_audio(audio_path: str | Path, config: AppConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    """Load an audio file and convert it to 16 kHz mono."""

    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    quality_issues: list[str] = []
    if path.suffix.lower() not in config.supported_extensions:
        quality_issues.append(f"unsupported_extension:{path.suffix.lower()}")

    raw_audio: np.ndarray | None = None
    sample_rate = config.target_sample_rate
    channels = 1

    loaders = [_load_with_soundfile]
    if path.suffix.lower() == ".wav":
        loaders.append(_load_with_wave)
    loaders.extend((_load_with_librosa, _load_with_ffmpeg))

    for loader in loaders:
        try:
            raw_audio, sample_rate, channels = loader(path)
            break
        except Exception:
            raw_audio = None

    if raw_audio is None:
        raise ValueError(f"Failed to decode audio file: {path}")

    if raw_audio.ndim == 2:
        mono = np.mean(raw_audio, axis=0)
    else:
        mono = raw_audio

    mono = np.nan_to_num(np.asarray(mono, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)

    if sample_rate != config.target_sample_rate:
        try:
            import librosa

            mono = librosa.resample(mono, orig_sr=sample_rate, target_sr=config.target_sample_rate)
        except Exception:
            mono = _resample_linear(mono, orig_sr=sample_rate, target_sr=config.target_sample_rate)
        sample_rate = config.target_sample_rate

    duration_sec = len(mono) / sample_rate if len(mono) else 0.0
    if len(mono) == 0:
        quality_issues.append("empty_audio")
    if duration_sec < config.min_duration_sec:
        quality_issues.append("too_short")
    if duration_sec > config.max_duration_sec:
        quality_issues.append("too_long")

    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    if peak >= 0.999:
        quality_issues.append("possible_clipping")

    return {
        "audio": mono,
        "audio_meta": {
            "duration_sec": round(float(duration_sec), 3),
            "sample_rate": int(sample_rate),
            "channels": int(channels),
            "quality_ok": len(quality_issues) == 0,
            "quality_issues": quality_issues,
        },
    }
