"""语音播报（TTS）：Edge-TTS 为主，系统原生兜底。

- edge-tts：免费、免 Key，晓晓/云希音色自然（需联网）
- macOS `say`：离线零延迟兜底（联网失败时自动降级）
- Windows SAPI / Linux espeak-ng：最后兜底，保证"永远说得出话"
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time

import numpy as np

from . import config
from .audio import BargeWatcher, default_output_sample_rate, play_pcm

logger = logging.getLogger("sofa-coder")

_EDGE_MP3_CACHE_TTS = "edge-tts 合成音频（mp3）"


def _decode_mp3_to_pcm(mp3: bytes) -> tuple[np.ndarray, int]:
    import miniaudio

    out_sr = default_output_sample_rate()
    decoded = miniaudio.decode(
        mp3,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=out_sr,
        dither=miniaudio.DitherMode.NONE,
    )
    pcm = np.frombuffer(decoded.samples, dtype=np.int16)
    return pcm, out_sr


def _speak_edge(text: str, watcher: BargeWatcher | None) -> bool:
    import asyncio

    import edge_tts

    async def _synth() -> bytes:
        com = edge_tts.Communicate(text, voice=config.TTS_VOICE)
        return b"".join(
            chunk["data"] async for chunk in com.stream() if chunk["type"] == "audio"
        )

    mp3 = asyncio.run(_synth())
    if not mp3:
        raise RuntimeError("edge-tts 返回了空音频")
    pcm, sr = _decode_mp3_to_pcm(mp3)
    return play_pcm(pcm, sr, watcher)


def _speak_mac_say(text: str, watcher: BargeWatcher | None) -> bool:
    proc = subprocess.Popen(
        ["say", "-v", config.MAC_SAY_VOICE, text],  # noqa: S603,S607
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    while proc.poll() is None:
        if watcher is not None and watcher.poll():
            proc.kill()
            return True
        time.sleep(0.05)
    return watcher is not None and watcher.triggered


def _speak_win_sapi(text: str, watcher: BargeWatcher | None) -> bool:
    script = (
        'Add-Type -AssemblyName System.Speech; '
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak(@'\n{text}\n'@)"
    )
    proc = subprocess.Popen(  # noqa: S603
        ["powershell", "-NoProfile", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.wait()  # Windows 兜底不做打断，能用就行
    return False


def _speak_linux(text: str, watcher: BargeWatcher | None) -> bool:
    proc = subprocess.Popen(  # noqa: S603,S607
        ["espeak-ng", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    while proc.poll() is None:
        if watcher is not None and watcher.poll():
            proc.kill()
            return True
        time.sleep(0.05)
    return watcher is not None and watcher.triggered


def _available_engines() -> list[str]:
    """按配置与平台给出 TTS 引擎尝试顺序。"""
    if config.TTS_ENGINE == "off":
        return []
    if config.TTS_ENGINE == "edge":
        return ["edge"]
    if config.TTS_ENGINE == "say":
        return ["native"]
    engines = ["edge"]
    if config.IS_MAC:
        engines.append("native")
    elif config.IS_WIN:
        engines.append("sapi")
    else:
        engines.append("espeak")
    return engines


_speak_lock = threading.Lock()


def speak(text: str, watcher: BargeWatcher | None = None) -> bool:
    """播报一段话，返回是否被用户打断。任何引擎失败自动降级到系统原生。"""
    text = text.strip()
    if not text:
        return False
    with _speak_lock:
        if config.DRY_RUN:
            logger.info("[TTS·dry] %s", text)
            return False
        last_exc: Exception | None = None
        for engine in _available_engines():
            try:
                if engine == "edge":
                    return _speak_edge(text, watcher)
                if engine == "native":
                    return _speak_mac_say(text, watcher)
                if engine == "sapi":
                    return _speak_win_sapi(text, watcher)
                if engine == "espeak":
                    return _speak_linux(text, watcher)
            except Exception as exc:  # 网络抖动/引擎缺失 → 换下一个引擎
                last_exc = exc
                logger.warning("TTS 引擎 %s 失败：%s，尝试降级", engine, exc)
        logger.error("所有 TTS 引擎都失败了：%s", last_exc)
        sys.stderr.write(f"[sofa-coder] 播报失败：{text}\n")
        return False
