"""T30 - HOMI-C LiveKit audio bridge.

Topology (option B of the T30 contract: the canonical HOMI-D entry point
performs the single STT inference and the single semantic turn):

    LiveKit room (private)
        -> this bridge (participant tecnico autorizado, HOMI-C)
        -> audio frames via AudioStream, normalized to PCM
        -> VAD / endpointing (bounded buffer)
        -> HOMI-D  POST /v1/voice/transcribe   (canonical entry point)
              -> HOMI-C STT   (one single inference)
              -> HOMI-D semantic turn -> HOMI-A THINK real
              -> HOMI-D tools / policy
              -> HOMI-C SPEAK  (Chatterbox ES-AR real)
        -> answer audio downloaded through the authenticated binary route
        -> published as a LiveKit LocalAudioTrack

The bridge NEVER runs tools, NEVER runs THINK and NEVER synthesizes speech
by itself: LiveKit is transport only, the product authority stays in
HOMI-D.

The bridge subscribes EXCLUSIVELY to the user microphone track. Its own
published track is never subscribed by itself, so Homi never captures its
own voice as a new user turn.
"""

from __future__ import annotations

import array
import asyncio
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import wave
from typing import Optional

from livekit import rtc

# --------------------------------------------------------------------------- #
# Configuration (environment only, never hardcoded secrets)
# --------------------------------------------------------------------------- #

HOMI_D_BASE = os.getenv("HOMI_D_BASE", "http://100.81.185.53:8000").rstrip("/")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://100.81.185.53:7880")
LIVEKIT_ROOM = os.getenv("LIVEKIT_ROOM", "homi_t30_bridge")
BRIDGE_TOKEN = os.getenv("BRIDGE_HOMI_TOKEN", "")
BRIDGE_HOUSEHOLD = os.getenv("BRIDGE_HOUSEHOLD_ID", "homi-t30")
BRIDGE_ACTOR = os.getenv("BRIDGE_ACTOR_ID", "homi-bridge-c")
CONVERSATION_ID = os.getenv("BRIDGE_CONVERSATION_ID", "conv_t30_bridge_c")

STT_SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2

# Endpointing (T30 conservador)
SILENCE_RMS = 450.0
SILENCE_SECONDS = 1.4
MIN_SPEECH_SECONDS = 0.6
MAX_TURN_SECONDS = 25.0
PRE_ROLL_SECONDS = 0.35

# T31 — deteccion de inicio de habla y barge-in.
# El inicio exige varios frames consecutivos por encima de SPEECH_RMS para no
# abrir un turno por ruido aislado. El barge-in exige un umbral claramente
# superior y sostenido, y una ventana muerta al comenzar la reproduccion para
# no confundir el eco del altavoz con la voz del usuario.
SPEECH_RMS = 700.0
SPEECH_ON_FRAMES = 3
BARGE_IN_RMS = 1400.0
BARGE_IN_SUSTAIN_S = 0.30
BARGE_IN_GUARD_S = 0.45
MAX_PENDING_TURNS = 1
MIN_TURN_BYTES = int(STT_SAMPLE_RATE * 2 * MIN_SPEECH_SECONDS)
MAX_BUFFER_BYTES = int(MAX_TURN_SECONDS * STT_SAMPLE_RATE * 2)

LOG_PREFIX = "[bridge-c]"


def log(message: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(f"{LOG_PREFIX} {message}", flush=True)


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #

def http_json(
    url: str,
    payload: Optional[dict] = None,
    headers: Optional[dict] = None,
    method: str = "POST",
    timeout: float = 180.0,
) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def http_bytes(url: str, headers: Optional[dict] = None, timeout: float = 120.0) -> bytes:
    request = urllib.request.Request(url, method="GET")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {BRIDGE_TOKEN}",
        "X-Household-Id": BRIDGE_HOUSEHOLD,
        "X-Actor-Id": BRIDGE_ACTOR,
    }


def request_livekit_token() -> tuple[str, str]:
    """Ask HOMI-D (the authority) for a LiveKit token for this bridge.

    Returns (token, room). The room is the one HOMI-D authorized: the
    bridge NEVER picks a room by itself.
    """
    url = f"{HOMI_D_BASE}/v1/livekit/token?conversation_id={CONVERSATION_ID}"
    payload = http_json(url, headers=auth_headers(), method="POST", timeout=30.0)
    token = payload.get("token")
    room = payload.get("room")
    if not token or not room:
        raise RuntimeError("HOMI-D did not return a LiveKit token")
    log(f"livekit token ok (room={room})")
    return token, room


def _as_bytes(data) -> bytes:
    """Return the raw PCM bytes of a LiveKit audio frame payload.

    ``AudioFrame.data`` is a memoryview cast to int16, so it must be
    flattened to bytes before it can be measured or written to a WAV file.
    """
    if data is None:
        return b""
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    try:
        return bytes(memoryview(data).cast("B"))
    except Exception:
        try:
            return bytes(data)
        except Exception:
            return b""


def _wav_to_pcm16(audio: bytes) -> tuple[bytes, int, int]:
    """Decode a WAV payload to PCM16, whatever the source bit depth.

    Chatterbox ES-AR answers are 32 bit FLOAT WAV, which the ``wave``
    module cannot read and LiveKit cannot publish.
    """
    try:
        with wave.open(io.BytesIO(audio), "rb") as handle:
            width = handle.getsampwidth()
            rate = handle.getframerate()
            channels = handle.getnchannels()
            if width == SAMPLE_WIDTH:
                return handle.readframes(handle.getnframes()), rate, channels
    except Exception:
        pass

    import subprocess
    import tempfile

    ffmpeg = os.getenv("HOMI_FFMPEG_PATH") or _find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to decode the answer audio")

    src_fd, src_path = tempfile.mkstemp(suffix=".wav")
    dst_fd, dst_path = tempfile.mkstemp(suffix=".wav")
    os.close(dst_fd)
    try:
        with os.fdopen(src_fd, "wb") as handle:
            handle.write(audio)
        subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-i", src_path, "-f", "wav", "-acodec", "pcm_s16le",
                dst_path,
            ],
            capture_output=True,
            timeout=120,
            check=True,
        )
        with open(dst_path, "rb") as handle:
            converted = handle.read()
    finally:
        for path in (src_path, dst_path):
            try:
                os.unlink(path)
            except Exception:
                pass

    with wave.open(io.BytesIO(converted), "rb") as handle:
        return (
            handle.readframes(handle.getnframes()),
            handle.getframerate(),
            handle.getnchannels(),
        )


def _find_ffmpeg() -> Optional[str]:
    import shutil

    explicit = os.getenv("HOMI_FFMPEG_PATH")
    if explicit and os.path.isfile(explicit):
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    for extra in (
        r"C:\Homi\tools\ffmpeg-8.1.2\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe",
        r"C:\Homi\tools\ffmpeg\bin\ffmpeg.exe",
    ):
        if os.path.isfile(extra):
            return extra
    return None


def pcm_to_wav(pcm: bytes, sample_rate: int = STT_SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(SAMPLE_WIDTH)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# Turn accumulation
# --------------------------------------------------------------------------- #

class TurnAccumulator:
    """Bounded PCM accumulator with VAD, endpointing and barge-in detection."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.speaking = False
        self.last_voice_at = 0.0
        self.started_at = 0.0
        self.total_bytes = 0
        self.frames = 0
        self.max_rms = 0.0
        # T31
        self.speech_candidate = 0
        self.speech_start_bytes = 0
        self.playback_active = False
        self.playback_started_at = 0.0
        self.barge_hold_started_at = 0.0
        self.barge_in = False

    def push(self, data) -> bool:
        """Push one frame. Returns True only when a real endpoint was reached."""
        if data is None:
            return False
        raw = _as_bytes(data)
        if not raw:
            return False
        now = time.time()
        self.buffer.extend(raw)
        self.total_bytes += len(raw)
        self.frames += 1
        # Hard bound even if the user never pauses.
        if len(self.buffer) > MAX_BUFFER_BYTES:
            excess = len(self.buffer) - MAX_BUFFER_BYTES
            excess -= excess % 2
            if excess > 0:
                del self.buffer[:excess]

        samples = array.array("h")
        try:
            samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
        except Exception:
            samples = array.array("h")

        rms = 0.0
        if len(samples) > 0:
            rms = (sum(value * value for value in samples) / len(samples)) ** 0.5
        if rms > self.max_rms:
            self.max_rms = rms
        if self.frames % 100 == 0:
            log(
                f"vad frame #{self.frames} rms={rms:.0f} max_rms={self.max_rms:.0f} "
                f"speaking={self.speaking} playback={self.playback_active} "
                f"buffered={self.total_bytes}"
            )

        # While HOMI speaks, mic frames are only watched for barge-in. They
        # stay in the buffer as pre-roll for the NEXT turn; no endpoint fires.
        if self.playback_active:
            guarded = now - self.playback_started_at >= BARGE_IN_GUARD_S
            if guarded and rms >= BARGE_IN_RMS:
                if self.barge_hold_started_at == 0.0:
                    self.barge_hold_started_at = now
                elif now - self.barge_hold_started_at >= BARGE_IN_SUSTAIN_S:
                    self.barge_in = True
                    log(f"barge-in detected (rms={rms:.0f})")
            else:
                self.barge_hold_started_at = 0.0
            return False

        # Conservative speech onset: several consecutive frames over SPEECH_RMS.
        if rms >= SPEECH_RMS:
            if self.speech_candidate == 0 and not self.speaking:
                self.speech_candidate = 1
            else:
                self.speech_candidate += 1
            if not self.speaking and self.speech_candidate >= SPEECH_ON_FRAMES:
                self.speaking = True
                self.started_at = now
                # Relative to the CURRENT (bounded) buffer: total_bytes is
                # cumulative and would defeat the pre-roll trim below.
                self.speech_start_bytes = len(self.buffer)
                log(f"speech detected (rms={rms:.0f})")
            if self.speaking:
                self.last_voice_at = now
        else:
            self.speech_candidate = 0
            if self.speaking:
                silence_for = now - self.last_voice_at
                speech_for = self.last_voice_at - self.started_at
                if silence_for >= SILENCE_SECONDS and speech_for >= MIN_SPEECH_SECONDS:
                    self.speaking = False
                    log(
                        f"endpoint detected (speech={speech_for:.1f}s "
                        f"silence={silence_for:.1f}s)"
                    )
                    return True
                if now - self.started_at >= MAX_TURN_SECONDS:
                    self.speaking = False
                    log("endpoint detected (max turn duration)")
                    return True
        return False

    def take(self) -> bytes:
        # Keep only PRE_ROLL_SECONDS of silence before the first speech frame.
        trim = self.speech_start_bytes - int(
            PRE_ROLL_SECONDS * STT_SAMPLE_RATE * SAMPLE_WIDTH
        )
        if trim > 0 and trim < len(self.buffer):
            trim -= trim % 2
            del self.buffer[:trim]
        pcm = bytes(self.buffer)
        self.buffer = bytearray()
        self.total_bytes = 0
        self.speaking = False
        self.speech_candidate = 0
        self.speech_start_bytes = 0
        self.barge_hold_started_at = 0.0
        return pcm


# --------------------------------------------------------------------------- #
# Bridge
# --------------------------------------------------------------------------- #

class Bridge:
    def __init__(self) -> None:
        self.room: Optional[rtc.Room] = None
        self.accumulator = TurnAccumulator()
        self.publisher: Optional[rtc.LocalAudioTrack] = None
        self.source: Optional[rtc.AudioSource] = None
        self.busy = False
        # T31 — Turn/generation lifecycle owned by HOMI-D.
        self.turn_seq = 0
        self.generation_id: Optional[str] = None
        self.cancel_event = asyncio.Event()
        self.pending_turns: list[bytes] = []

    async def connect(self) -> None:
        token, room_name = request_livekit_token()
        self.room = rtc.Room()
        await self.room.connect(LIVEKIT_URL, token)
        log(f"connected to {LIVEKIT_URL} room={room_name}")

        def on_track(track, publication, participant):
            asyncio.create_task(self._consume(track, participant))

        self.room.on("track_subscribed", on_track)

    async def publish_event(self, event: str, **fields) -> None:
        """T31 — emit turn events to the client through reliable LiveKit data."""
        if self.room is None:
            return
        try:
            payload = {"event": event, "conversation_id": CONVERSATION_ID}
            payload.update(fields)
            await self.room.local_participant.publish_data(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                reliable=True,
            )
        except Exception as exc:  # pragma: no cover - transport level
            log(f"publish event {event} failed: {exc!r}")

    async def _consume(self, track, participant) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return

        log(f"audio track subscribed from {participant.identity}")
        stream = rtc.AudioStream(track)
        seen = 0
        try:
            async for event in stream:
                frame = event.frame
                seen += 1
                if seen <= 3 or seen % 200 == 0:
                    log(
                        f"frame #{seen} rate={frame.sample_rate} ch={frame.num_channels} "
                        f"bytes={len(_as_bytes(frame.data))}"
                    )

                pcm = _as_bytes(frame.data)
                if frame.sample_rate != STT_SAMPLE_RATE or frame.num_channels != CHANNELS:
                    # HOMI-C normalizes to mono 16 kHz before STT.
                    pcm = _resample_to_16k_mono(pcm, frame.sample_rate, frame.num_channels)

                was_speaking = self.accumulator.speaking
                endpoint = self.accumulator.push(pcm)

                if not was_speaking and self.accumulator.speaking:
                    await self.publish_event("voice_start")

                # T31 — valid barge-in: stop the old answer, invalidate its
                # generation and let these same frames seed the next turn.
                if self.accumulator.barge_in:
                    self.accumulator.barge_in = False
                    await self._on_barge_in()
                    continue

                if endpoint:
                    await self.publish_event("voice_end")
                    captured = self.accumulator.take()
                    if len(captured) >= MIN_TURN_BYTES:
                        await self._enqueue_turn(captured)
                    else:
                        log(f"empty turn rejected ({len(captured)} bytes)")
        except Exception as exc:  # pragma: no cover - transport level
            log(f"audio stream error after {seen} frames: {exc!r}")

    async def _enqueue_turn(self, pcm: bytes) -> None:
        """T31 — never drop an utterance that arrives during processing."""
        if self.busy:
            self.pending_turns.append(pcm)
            if len(self.pending_turns) > MAX_PENDING_TURNS:
                self.pending_turns.pop(0)
            log("turn queued while pipeline was busy (not dropped)")
            return
        await self._process_turn(pcm)

    async def _on_barge_in(self) -> None:
        """T31 — stop playback and invalidate the generation in HOMI-D."""
        acc = self.accumulator
        generation = self.generation_id
        log(f"barge-in while generation={generation}")
        await self.publish_event("barge_in", generation_id=generation)
        self.cancel_event.set()

        # Seed VAD state so a normal endpoint closes the NEW utterance.
        acc.speaking = True
        acc.started_at = acc.barge_hold_started_at or time.time()
        acc.last_voice_at = time.time()
        acc.speech_start_bytes = max(
            0,
            len(acc.buffer)
            - int(BARGE_IN_SUSTAIN_S * STT_SAMPLE_RATE * SAMPLE_WIDTH),
        )
        acc.barge_hold_started_at = 0.0

        if generation:
            try:
                await asyncio.to_thread(
                    http_json,
                    f"{HOMI_D_BASE}/v1/voice/interrupt",
                    {
                        "conversation_id": CONVERSATION_ID,
                        "generation_id": generation,
                    },
                    auth_headers(),
                )
                log(f"generation {generation} invalidated in HOMI-D")
            except Exception as exc:
                log(f"interrupt call failed: {exc!r}")


    async def _process_turn(self, pcm: bytes) -> None:
        if self.busy:
            self.pending_turns.append(pcm)
            return
        self.busy = True
        started = time.time()
        generation: Optional[str] = None
        try:
            self.turn_seq += 1
            turn_id = f"turn_t31_{int(time.time() * 1000)}_{self.turn_seq:04d}"
            self.cancel_event.clear()

            # T31 — HOMI-D is the only authority for generation ids.
            try:
                opened = await asyncio.to_thread(
                    http_json,
                    f"{HOMI_D_BASE}/v1/voice/turn/begin",
                    {
                        "conversation_id": CONVERSATION_ID,
                        "turn_id": turn_id,
                    },
                    auth_headers(),
                )
                generation = opened.get("generation_id")
                self.generation_id = generation
            except Exception as exc:
                log(f"turn begin failed: {exc!r}")
                return

            wav = pcm_to_wav(pcm)
            log(
                f"turn captured: {len(pcm)} bytes "
                f"({len(pcm) / 2 / STT_SAMPLE_RATE:.1f}s) generation={generation}"
            )

            try:
                # Non blocking: the event loop must stay free to detect
                # barge-in while the real STT/THINK/TTS pipeline runs.
                result = await asyncio.to_thread(self._post_turn, wav, generation, turn_id)
            except Exception as exc:
                log(f"turn failed: {exc!r}")
                return

            transcript = (result.get("transcript") or "").strip()
            spoken = (result.get("spoken_text") or result.get("answer") or "").strip()
            audio_id = result.get("audio_id")
            response_turn_id = result.get("turn_id")

            log(
                f"turn {response_turn_id}: transcript={transcript!r} "
                f"spoken={spoken!r} audio_id={audio_id!r} "
                f"speech_status={result.get('speech_status')!r}"
            )

            await self.publish_event(
                "transcript_final",
                generation_id=generation,
                turn_id=response_turn_id,
                transcript=transcript,
            )

            if result.get("status") == "interrupted" or self.cancel_event.is_set():
                log("generation interrupted; discarding result before playback")
                return

            if audio_id:
                try:
                    audio = await asyncio.to_thread(
                        http_bytes,
                        f"{HOMI_D_BASE}/v1/voice/audio/{audio_id}",
                        auth_headers(),
                        120.0,
                    )
                    if self.cancel_event.is_set():
                        log("late audio discarded (generation invalidated)")
                        return
                    await self.publish_event(
                        "speech_start",
                        generation_id=generation,
                        turn_id=response_turn_id,
                    )
                    await self.publish_audio(audio, generation)
                    log(f"published {len(audio)} bytes of answer audio")
                except Exception as exc:
                    log(f"publish failed: {exc!r}")

            log(f"turn latency: {time.time() - started:.2f}s")
        finally:
            self.busy = False
            if self.pending_turns:
                queued = self.pending_turns.pop(0)
                asyncio.create_task(self._process_turn(queued))

    def _post_turn(
        self,
        wav: bytes,
        generation: Optional[str],
        turn_id: Optional[str] = None,
    ) -> dict:
        """POST the captured audio to the canonical HOMI-D voice entry point."""
        boundary = "----homiT30BridgeBoundary"
        parts = [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="turn.wav"\r\n',
            b"Content-Type: audio/wav\r\n\r\n",
            wav,
        ]
        fields = [("conversation_id", CONVERSATION_ID)]
        if turn_id:
            fields.append(("turn_id", turn_id))
        if generation:
            fields.append(("generation_id", generation))
        for key, value in fields:
            parts.extend(
                [
                    f"\r\n--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                    str(value).encode("utf-8"),
                ]
            )
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        body = b"".join(parts)

        request = urllib.request.Request(
            f"{HOMI_D_BASE}/v1/voice/transcribe", data=body, method="POST"
        )
        request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        for key, value in auth_headers().items():
            request.add_header(key, value)

        with urllib.request.urlopen(request, timeout=180.0) as response:
            return json.loads(response.read().decode("utf-8"))

    async def publish_audio(self, audio: bytes, generation: Optional[str]) -> None:
        """Publish the real answer audio as a LiveKit track (barge-in aware)."""
        pcm, sample_rate, channels = _wav_to_pcm16(audio)
        if not pcm:
            raise RuntimeError("the answer audio could not be decoded")

        source = rtc.AudioSource(sample_rate, channels)
        track = rtc.LocalAudioTrack.create_audio_track("homi", source)
        await self.room.local_participant.publish_track(track)
        self.source = source
        self.publisher = track

        acc = self.accumulator
        acc.playback_active = True
        acc.playback_started_at = time.time()
        acc.barge_hold_started_at = 0.0
        samples_per_chunk = int(sample_rate * 0.02)
        chunk_bytes = samples_per_chunk * SAMPLE_WIDTH * channels
        offset = 0
        published_samples = 0
        interrupted = False
        try:
            while offset < len(pcm):
                if self.cancel_event.is_set():
                    interrupted = True
                    log("barge-in: stop publishing; late fragments discarded")
                    break
                chunk = pcm[offset : offset + chunk_bytes]
                if len(chunk) < chunk_bytes:
                    break
                frame = rtc.AudioFrame(
                    bytearray(chunk), sample_rate, channels, samples_per_chunk
                )
                await source.capture_frame(frame)
                published_samples += samples_per_chunk
                offset += chunk_bytes
                await asyncio.sleep(0.02)
        finally:
            acc.playback_active = False
            interrupted = interrupted or self.cancel_event.is_set()
            await source.aclose()
            try:
                await self.room.local_participant.unpublish_track(track)
            except Exception:
                pass
            self.source = None
            self.publisher = None
            await self.publish_event(
                "speech_end",
                generation_id=generation,
                delivered_s=published_samples / max(1, sample_rate),
                interrupted=interrupted,
            )
            if generation:
                # T31 — generated vs delivered: an interrupted answer is never
                # recorded as completely delivered.
                try:
                    await asyncio.to_thread(
                        http_json,
                        f"{HOMI_D_BASE}/v1/voice/delivery",
                        {
                            "conversation_id": CONVERSATION_ID,
                            "generation_id": generation,
                            "delivered_s": published_samples / max(1, sample_rate),
                            "duration_s": len(pcm) / (SAMPLE_WIDTH * max(1, sample_rate)),
                            "interrupted": interrupted,
                        },
                        auth_headers(),
                    )
                    log(
                        f"delivery recorded: interrupted={interrupted} "
                        f"delivered_s={published_samples / max(1, sample_rate):.2f}"
                    )
                except Exception as exc:
                    log(f"delivery report failed: {exc!r}")

    async def run(self) -> None:
        await self.connect()
        while True:
            await asyncio.sleep(1)


def _resample_to_16k_mono(pcm: bytes, source_rate: int, channels: int) -> bytes:
    """Normalize raw PCM to mono 16 kHz PCM16."""
    samples = array.array("h")
    try:
        samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    except Exception:
        samples = array.array("h")

    channels = max(1, channels)
    if channels > 1:
        mono = array.array("h", [0] * (len(samples) // channels))
        for index in range(len(mono)):
            total = 0
            for channel in range(channels):
                position = index * channels + channel
                if position < len(samples):
                    total += samples[position]
            mono[index] = int(total / channels)
        samples = mono

    source_rate = source_rate or STT_SAMPLE_RATE
    if source_rate != STT_SAMPLE_RATE and len(samples) > 0:
        ratio = source_rate / STT_SAMPLE_RATE
        target = int(len(samples) / ratio)
        resampled = array.array("h", [0] * target)
        for index in range(target):
            position = int(index * ratio)
            resampled[index] = samples[min(position, len(samples) - 1)]
        samples = resampled

    return samples.tobytes()


if __name__ == "__main__":
    if not BRIDGE_TOKEN:
        log("BRIDGE_HOMI_TOKEN is required")
        sys.exit(2)
    try:
        asyncio.run(Bridge().run())
    except KeyboardInterrupt:
        log("stopped")
