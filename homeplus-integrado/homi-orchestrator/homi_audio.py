"""T30 - Audio utilities for the voice turn pipeline (HOMI-D side).

Responsibilities:

* Detect the real format of an uploaded audio payload (never trust the
  file extension only).
* Convert it, server side, to the canonical PCM WAV (mono, 16 kHz, 16 bit)
  that the HOMI-C STT (faster-whisper) consumes.
* Extract the WAV payload of a generated answer so it can be delivered to
  a client (Expo Go iOS / LiveKit) without a second synthesis.

The canonical conversion uses FFmpeg. FFmpeg is already installed on
HOMI-D and on HOMI-C; it is discovered through PATH or through the known
local tool directory. When FFmpeg is not available the module fails closed
for non-WAV payloads instead of shipping an undecodable file to the STT.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from io import BytesIO as _BytesIO
from typing import Optional

# Canonical STT input format.
STT_SAMPLE_RATE = 16000
STT_CHANNELS = 1
STT_SAMPLE_WIDTH = 2  # 16 bit

# Formats the STT provider accepts (stt_config.json -> allowed_formats).
ALLOWED_STT_FORMATS = ("wav", "mp3", "flac", "ogg", "m4a")

MAX_AUDIO_BYTES = 50 * 1024 * 1024

_EXTRA_FFMPEG_DIRS = (
    r"C:\Homi\tools\ffmpeg-8.1.2\ffmpeg-8.1.2-full_build\bin",
    r"C:\Homi\tools\ffmpeg\bin",
)

# Magic bytes used to detect the real container/codec of a payload.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"RIFF", "wav"),
    (b"OggS", "ogg"),
    (b"fLaC", "flac"),
    (b"ID3", "mp3"),
    (b"\xff\xfb", "mp3"),
    (b"\xff\xf3", "mp3"),
    (b"\xff\xf2", "mp3"),
    (b"\x1a\x45\xdf\xa3", "m4a"),
)


def ffmpeg_path() -> Optional[str]:
    """Return the ffmpeg executable path, or None when it is not available."""
    explicit = os.getenv("HOMI_FFMPEG_PATH")
    if explicit and os.path.isfile(explicit):
        return explicit

    found = shutil.which("ffmpeg")
    if found:
        return found

    for extra in _EXTRA_FFMPEG_DIRS:
        candidate = os.path.join(extra, "ffmpeg.exe")
        if os.path.isfile(candidate):
            return candidate

    return None


def detect_format(data: bytes, declared: Optional[str] = None) -> str:
    """Detect the real audio format from the payload magic bytes.

    ``declared`` (the client hint) is only used as a fallback when the
    payload carries no recognizable magic bytes.
    """
    if data:
        for magic, name in _MAGIC:
            if data.startswith(magic):
                return name
        # ISO base media (m4a/mp4) without a leading ftyp at offset 4.
        if len(data) > 12 and data[4:8] == b"ftyp":
            return "m4a"

    hint = (declared or "").strip().lower().lstrip(".")
    if hint in ALLOWED_STT_FORMATS:
        return hint

    return "wav"


def _run_ffmpeg(args: list[str], timeout: float = 120.0) -> tuple[bool, str]:
    exe = ffmpeg_path()
    if not exe:
        return False, "ffmpeg_not_available"

    try:
        proc = subprocess.run(
            [exe, "-hide_banner", "-loglevel", "error", "-nostdin", *args],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "ffmpeg_timeout"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"ffmpeg_error:{exc}"

    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", "replace").strip()
        return False, f"ffmpeg_failed:{stderr[:200]}"

    return True, ""


def to_canonical_wav(data: bytes, fmt: str) -> tuple[Optional[bytes], str]:
    """Convert an audio payload to mono 16 kHz 16 bit PCM WAV.

    Returns ``(wav_bytes, error)``. ``wav_bytes`` is None when the
    conversion failed; ``error`` is empty on success.
    """
    if not data:
        return None, "audio_empty"

    if len(data) > MAX_AUDIO_BYTES:
        return None, "audio_too_large"

    fmt = (fmt or "wav").lower()
    if fmt == "wav":
        ok, err = _is_canonical_wav(data)
        if ok:
            return data, ""
        # Not canonical (wrong rate/channels/width): still convertible.

    return _convert_with_temp_files(data, fmt)


def _convert_with_temp_files(data: bytes, fmt: str) -> tuple[Optional[bytes], str]:
    exe = ffmpeg_path()
    if not exe:
        return None, "ffmpeg_not_available"

    src_suffix = f".{fmt}" if fmt in ALLOWED_STT_FORMATS else ".bin"
    src_fd, src_path = tempfile.mkstemp(suffix=src_suffix)
    dst_fd, dst_path = tempfile.mkstemp(suffix=".wav")
    os.close(dst_fd)
    try:
        with os.fdopen(src_fd, "wb") as handle:
            handle.write(data)

        try:
            proc = subprocess.run(
                [
                    exe,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-y",
                    "-i",
                    src_path,
                    "-f",
                    "wav",
                    "-acodec",
                    "pcm_s16le",
                    "-ar",
                    str(STT_SAMPLE_RATE),
                    "-ac",
                    str(STT_CHANNELS),
                    dst_path,
                ],
                capture_output=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None, "ffmpeg_timeout"

        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", "replace").strip()
            return None, f"ffmpeg_failed:{stderr[:200]}"

        with open(dst_path, "rb") as handle:
            converted = handle.read()

        if not converted:
            return None, "ffmpeg_empty_output"

        return converted, ""
    finally:
        for path in (src_path, dst_path):
            try:
                os.unlink(path)
            except Exception:
                pass


def _is_canonical_wav(data: bytes) -> tuple[bool, str]:
    """Validate that a WAV payload already is mono 16 kHz 16 bit."""
    try:
        with wave.open(_BytesIO(data), "rb") as handle:  # type: ignore[arg-type]
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
    except Exception:
        return False, "wav_unreadable"

    if channels == STT_CHANNELS and width == STT_SAMPLE_WIDTH and rate == STT_SAMPLE_RATE:
        return True, ""

    return False, "wav_not_canonical"


def to_pcm16_wav(data: bytes) -> tuple[Optional[bytes], str]:
    """Normalize a WAV payload to 16 bit PCM, preserving its sample rate.

    Chatterbox ES-AR returns 32 bit FLOAT WAV. LiveKit audio tracks and the
    iOS player require 16 bit PCM, so the answer audio is normalized on the
    server instead of being re-encoded on the client.
    """
    if not data:
        return None, "audio_empty"

    # A WAV header carries the format tag at offset 20 (little endian).
    # 1 = PCM (16 bit), 3 = IEEE float (Chatterbox ES-AR output).
    fmt_tag = 0
    if len(data) >= 22 and data[:4] == b"RIFF":
        fmt_tag = int.from_bytes(data[20:22], "little")

    if fmt_tag == 1:
        try:
            with wave.open(_BytesIO(data), "rb") as handle:
                channels = handle.getnchannels()
                width = handle.getsampwidth()
                rate = handle.getframerate()
            if width == STT_SAMPLE_WIDTH:
                return data, ""
        except Exception:
            pass

    exe = ffmpeg_path()
    if not exe:
        return None, "ffmpeg_not_available"

    src_fd, src_path = tempfile.mkstemp(suffix=".wav")
    dst_fd, dst_path = tempfile.mkstemp(suffix=".wav")
    os.close(dst_fd)
    try:
        with os.fdopen(src_fd, "wb") as handle:
            handle.write(data)

        try:
            proc = subprocess.run(
                [
                    exe,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-y",
                    "-i",
                    src_path,
                    "-f",
                    "wav",
                    "-acodec",
                    "pcm_s16le",
                    dst_path,
                ],
                capture_output=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None, "ffmpeg_timeout"

        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", "replace").strip()
            return None, f"ffmpeg_failed:{stderr[:200]}"

        with open(dst_path, "rb") as handle:
            converted = handle.read()

        if not converted:
            return None, "ffmpeg_empty_output"

        return converted, ""
    finally:
        for path in (src_path, dst_path):
            try:
                os.unlink(path)
            except Exception:
                pass


def wav_payload(data: bytes) -> bytes:
    """Return the raw PCM payload of a WAV file (header removed)."""
    if data[:4] != b"RIFF":
        return data
    try:
        with wave.open(_BytesIO(data), "rb") as handle:  # type: ignore[arg-type]
            return handle.readframes(handle.getnframes())
    except Exception:
        return data[44:] if len(data) > 44 else data


def wav_info(data: bytes) -> dict:
    """Return basic WAV metadata (sample rate, channels, duration)."""
    try:
        with wave.open(_BytesIO(data), "rb") as handle:  # type: ignore[arg-type]
            rate = handle.getframerate()
            frames = handle.getnframes()
            return {
                "sample_rate": rate,
                "channels": handle.getnchannels(),
                "duration_s": round(frames / float(rate), 3) if rate else 0.0,
                "format": "wav",
            }
    except Exception:
        return {"sample_rate": None, "channels": None, "duration_s": None, "format": "wav"}
