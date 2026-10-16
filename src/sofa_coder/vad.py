"""免按键语音监听：Silero VAD（ONNX，无需 PyTorch）自动断句。

- Ear：常开 16kHz 麦克风，把 512 帧样本丢进队列
- SileroVAD：极轻量的 ONNX 推理（CPU 占用极低），兼容 v4/v5 两种模型导出格式
- listen_once：等用户开口 → 说完（默认停顿 1.5s）→ 返回整段 PCM
"""

from __future__ import annotations

import collections
import logging
import queue
import time
import urllib.request
from typing import Callable, Iterator

import numpy as np

from . import config

logger = logging.getLogger("sofa-coder")


class VadModelError(RuntimeError):
    """VAD 模型不可用（下载失败或推理引擎缺失）。"""


def ensure_vad_model() -> "pathlib.Path":
    """拿到本地 VAD 模型文件，不存在则自动下载（约 2MB，失败自动重试 3 次）。"""
    path = config.vad_model_path()
    if path.exists() and path.stat().st_size > 100_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("首次运行：正在下载 Silero VAD 模型（约 2MB）→ %s", path)
    tmp = path.with_suffix(".onnx.tmp")
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            urllib.request.urlretrieve(config.VAD_MODEL_URL, tmp)
            if tmp.stat().st_size <= 100_000:
                raise IOError("下载的模型文件不完整")
            tmp.replace(path)
            return path
        except Exception as exc:
            last_exc = exc
            logger.warning("VAD 模型下载失败（第 %d 次）：%s", attempt + 1, exc)
            time.sleep(1.5 * (attempt + 1))
    raise VadModelError(
        f"Silero VAD 模型下载失败（已重试 3 次）：{last_exc}\n"
        f"可以手动下载后放到：{path}\n"
        f"下载地址：{config.VAD_MODEL_URL}"
    ) from last_exc


class SileroVAD:
    """ONNX 版 Silero VAD，v4（h/c 状态）与 v5（state 状态）通吃。"""

    def __init__(self) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise VadModelError(
                "缺少 onnxruntime，请执行：pip install onnxruntime"
            ) from exc
        model_path = ensure_vad_model()
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._sess = ort.InferenceSession(
            str(model_path), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self._v5 = "state" in {i.name for i in self._sess.get_inputs()}
        self.reset()

    def reset(self) -> None:
        if self._v5:
            self._state: tuple | np.ndarray = np.zeros((2, 1, 128), dtype=np.float32)
        else:
            h = np.zeros((2, 1, 64), dtype=np.float32)
            self._state = (h, h.copy())

    def prob(self, frame: np.ndarray) -> float:
        """输入一帧 512 样本 int16，返回人声概率 0~1。"""
        x = frame.astype(np.float32) / 32768.0
        x = x.reshape(1, -1)
        if x.shape[1] != config.FRAME_SAMPLES:
            raise ValueError(f"VAD 帧长度应为 {config.FRAME_SAMPLES}，实际 {x.shape[1]}")
        if self._v5:
            out, state = self._sess.run(
                None,
                {
                    "input": x,
                    "state": self._state,
                    "sr": np.array(config.SAMPLE_RATE, dtype=np.int64),
                },
            )
            self._state = state
        else:
            h, c = self._state
            out, h2, c2 = self._sess.run(None, {"input": x, "h": h, "c": c})
            self._state = (h2, c2)
        return float(out[0][0])


class Ear:
    """麦克风监听器。用 with 语法开关；get_frame 从队列取 512 帧样本。"""

    def __init__(self) -> None:
        self._q: queue.Queue[np.ndarray] = queue.Queue(maxsize=400)
        self._stream = None
        self.dropped = 0

    def __enter__(self) -> "Ear":
        import sounddevice as sd

        def _cb(indata, frames, time_info, status):  # noqa: ANN001
            try:
                self._q.put_nowait(indata.copy().reshape(-1))
            except queue.Full:
                self.dropped += 1  # 队列满说明消费太慢，丢帧保实时

        self._stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=config.FRAME_SAMPLES,
            callback=_cb,
        )
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def get_frame(self, timeout: float | None = None) -> np.ndarray | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> None:
        """清空积压帧（播报结束后调用，避免 TTS 回声被当成指令）。"""
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                return


# 每帧时长（秒），16k/512 ≈ 32ms
_FRAME_S = config.FRAME_SAMPLES / config.SAMPLE_RATE


def listen_once(
    ear: Ear,
    vad: SileroVAD,
    *,
    silence_ms: int | None = None,
    max_s: float | None = None,
    on_speech_start: Callable[[], None] | None = None,
    timeout_s: float | None = None,
) -> np.ndarray | None:
    """听一句话：检测到连续人声开始录，停顿 silence_ms 后返回 PCM。

    - 超过 timeout_s 一直没人开口 → 返回 None
    - 说个没完超过 max_s → 强制截断返回已有内容
    - 内置 0.4s 预录音，避免吞掉第一个字
    """
    silence_ms = config.SILENCE_MS if silence_ms is None else silence_ms
    max_s = config.MAX_UTTERANCE_S if max_s is None else max_s
    timeout_s = config.FIRST_REPLY_TIMEOUT_S if timeout_s is None else timeout_s

    vad.reset()
    preroll = collections.deque(maxlen=int(0.4 / _FRAME_S))
    chunks: list[np.ndarray] = []
    started = False
    speech_run = 0
    silence_run = 0
    last_speech_idx = 0
    started_at = time.monotonic()

    while True:
        now = time.monotonic() - started_at
        if not started and now > timeout_s:
            return None
        if now > max_s:
            break

        frame = ear.get_frame(timeout=0.1)
        if frame is None:
            continue
        prob = vad.prob(frame)

        if not started:
            if prob >= config.VAD_THRESHOLD:
                speech_run += 1
                if speech_run >= 3:  # 连续 ~100ms 人声才算真开口，滤掉咳嗽键盘声
                    started = True
                    chunks.extend(preroll)
                    chunks.append(frame)
                    if on_speech_start:
                        on_speech_start()
            else:
                speech_run = 0
            preroll.append(frame)
        else:
            chunks.append(frame)
            if prob >= config.VAD_THRESHOLD * 0.9:
                silence_run = 0
                last_speech_idx = len(chunks)
            else:
                silence_run += _FRAME_S
                if silence_run * 1000 >= silence_ms:
                    break

    if not started:
        return None
    # 尾部留 0.25s 收尾，其余静音裁掉
    keep = min(len(chunks), max(last_speech_idx + int(0.25 / _FRAME_S), 1))
    return np.concatenate(chunks[:keep])


def iter_utterances(ear: Ear, vad: SileroVAD) -> Iterator[np.ndarray]:
    """连续听多句（自测 chat 模式用）。Ctrl-C 退出。"""
    while True:
        yield listen_once(ear, vad)
