"""音频输出层：提示音合成与可打断的 PCM 播放。

全部基于 sounddevice（macOS/Windows/Linux 通用，无需 ffmpeg）。
"""

from __future__ import annotations

import logging
import sys

import numpy as np

from . import config

logger = logging.getLogger("sofa-coder")
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(logging.INFO)

_SR = 24000  # 提示音内部合成采样率


def _tone(freq: float, dur_s: float, *, decay: float = 8.0, gain: float = 0.22) -> np.ndarray:
    t = np.linspace(0.0, dur_s, int(_SR * dur_s), endpoint=False)
    env = np.exp(-decay * t)
    wave = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2 * t)
    return (wave * env * gain * 32767).astype(np.int16)


def _concat(*parts: np.ndarray, gap_s: float = 0.0) -> np.ndarray:
    out: list[np.ndarray] = []
    for i, p in enumerate(parts):
        if i and gap_s > 0:
            out.append(np.zeros(int(_SR * gap_s), dtype=np.int16))
        out.append(p)
    return np.concatenate(out)


def make_chime(kind: str) -> np.ndarray:
    """合成三种提示音：ding=请说话，ack=收到开干，bye=再见。"""
    if kind == "ding":
        return _concat(_tone(1174.7, 0.16), _tone(1568.0, 0.22, gain=0.18), gap_s=0.03)
    if kind == "ack":
        return _concat(_tone(880.0, 0.10, gain=0.16), _tone(1174.7, 0.14, gain=0.14))
    if kind == "bye":
        return _concat(_tone(1046.5, 0.14, gain=0.16), _tone(784.0, 0.22, gain=0.14))
    raise ValueError(f"未知提示音类型: {kind}")


class BargeWatcher:
    """播报期间的"耳朵"：持续吞掉麦克风帧并检测人声，命中即打断播报。

    阈值比正常倾听更高（config.BARGE_IN_THRESHOLD），减少扬声器外放时
    TTS 回声造成的自我打断；戴耳机体验最佳，外放可用 SOFA_BARGE_IN=off。
    """

    def __init__(self, ear, vad) -> None:
        self.ear = ear
        self.vad = vad
        self.triggered = False
        self._run = 0

    def poll(self) -> bool:
        """消费当前积压的麦克风帧，返回是否已触发打断。"""
        if self.triggered:
            return True
        need = max(2, int(0.13 / (config.FRAME_SAMPLES / config.SAMPLE_RATE)))  # ~130ms 连续人声
        while True:
            frame = self.ear.get_frame(timeout=0)
            if frame is None:
                return self.triggered
            prob = self.vad.prob(frame)
            self._run = self._run + 1 if prob >= config.BARGE_IN_THRESHOLD else 0
            if self._run >= need:
                self.triggered = True
                logger.info("检测到用户插话（barge-in），停止播报")
                return True


def play_pcm(pcm: np.ndarray, sample_rate: int, watcher: BargeWatcher | None = None) -> bool:
    """分块播放 int16 PCM，watcher 存在时随时可被打断。返回是否被打断。"""
    if pcm.size == 0:
        return False
    import sounddevice as sd

    chunk = sample_rate // 10  # 100ms
    stream = sd.OutputStream(samplerate=sample_rate, channels=1, dtype="int16")
    with stream:
        for i in range(0, pcm.size, chunk):
            if watcher is not None and watcher.poll():
                return True
            stream.write(pcm[i : i + chunk])
    return False


def play_chime(kind: str) -> None:
    """播放一次性的提示音（不可打断，本来就不到半秒）。"""
    if not config.SOUND:
        return
    if config.DRY_RUN:
        logger.info("[提示音·dry] %s", kind)
        return
    try:
        play_pcm(make_chime(kind), _SR)
    except Exception as exc:  # 提示音失败不该中断主流程
        logger.warning("提示音播放失败（%s），已跳过", exc)


def default_output_sample_rate() -> int:
    try:
        import sounddevice as sd

        rate = sd.query_devices(None, "output")["default_samplerate"]
        return int(rate) or 48000
    except Exception:
        return 48000
