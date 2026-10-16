"""语音转文字（ASR）多后端适配。

设计：写代码经常中英夹杂（"把 header 的 padding 调大"），所以默认优先
对中英混说效果好的引擎。SOFA_ASR=auto 时的探测顺序：

1. groq   —— 配了 GROQ_API_KEY 就用（云端 whisper-large-v3-turbo，免费额度高、极快）
2. mlx    —— Apple Silicon 本地 mlx-whisper
3. funasr —— SenseVoiceSmall（中英混杂效果最佳，但依赖较大）
4. faster —— 跨平台 faster-whisper

四个都没装/没配 key 时抛出带安装指引的中文错误。
"""

from __future__ import annotations

import io
import logging
import re
import wave
from typing import Callable

import numpy as np

from . import config

logger = logging.getLogger("sofa-coder")

_SV_TAG_RE = re.compile(r"<\|[^|]*\|>")  # SenseVoice 输出里的 <|zh|><|NEUTRAL|> 标记


class AsrUnavailable(RuntimeError):
    """没有任何可用的 ASR 后端。"""


def strip_sensevoice_tags(text: str) -> str:
    return _SV_TAG_RE.sub("", text).strip()


def _to_float32(pcm: np.ndarray) -> np.ndarray:
    return pcm.astype(np.float32) / 32768.0


def _pcm_to_wav_bytes(pcm: np.ndarray, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


# --- 各后端实现（全部懒加载，模型进程内只建一次） -----------------------------


def _groq(pcm: np.ndarray) -> str:
    if not config.GROQ_API_KEY:
        raise AsrUnavailable("未配置 GROQ_API_KEY")
    import httpx

    wav = _pcm_to_wav_bytes(pcm)
    resp = httpx.post(
        f"{config.GROQ_BASE_URL}/audio/transcriptions",
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        files={"file": ("audio.wav", wav, "audio/wav")},
        data={
            "model": config.GROQ_MODEL,
            "response_format": "json",
            **({"language": config.ASR_LANGUAGE} if config.ASR_LANGUAGE != "auto" else {}),
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("text", "").strip()


def _mlx(pcm: np.ndarray) -> str:
    try:
        from mlx_whisper import transcribe
    except ImportError as exc:
        raise AsrUnavailable(
            "mlx-whisper 未安装（Apple Silicon 专用）。"
            "安装：uv tool install sofa-coder-mcp --with mlx-whisper"
        ) from exc
    result = transcribe(
        _to_float32(pcm),
        path_or_hf_repo=config.MLX_WHISPER_MODEL,
        language=None if config.ASR_LANGUAGE == "auto" else config.ASR_LANGUAGE,
    )
    return result.get("text", "").strip()


def _funasr(pcm: np.ndarray) -> str:
    try:
        from funasr import AutoModel
    except ImportError as exc:
        raise AsrUnavailable(
            "funasr 未安装（SenseVoiceSmall，中英混杂最佳）。"
            "安装：pip install \"sofa-coder-mcp[asr-funasr]\""
        ) from exc
    global _FUNASR_MODEL  # noqa: PLW0603
    if _FUNASR_MODEL is None:
        logger.info("首次加载 SenseVoiceSmall 模型（需要一些时间下载）……")
        _FUNASR_MODEL = AutoModel(
            model=config.FUNASR_MODEL, device="cpu", disable_pbar=True, disable_update=True
        )
    res = _FUNASR_MODEL.generate(
        input=_to_float32(pcm), cache={}, language="auto", use_itn=True
    )
    return strip_sensevoice_tags(res[0].get("text", ""))


_FUNASR_MODEL = None


def _faster(pcm: np.ndarray) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise AsrUnavailable(
            "faster-whisper 未安装（跨平台本地 Whisper）。"
            "安装：pip install \"sofa-coder-mcp[asr-faster]\""
        ) from exc
    global _FASTER_MODEL  # noqa: PLW0603
    if _FASTER_MODEL is None:
        logger.info("首次加载 faster-whisper/%s 模型……", config.FASTER_WHISPER_MODEL)
        _FASTER_MODEL = WhisperModel(
            config.FASTER_WHISPER_MODEL, device="cpu", compute_type="int8"
        )
    segments, _info = _FASTER_MODEL.transcribe(
        _to_float32(pcm),
        language=None if config.ASR_LANGUAGE == "auto" else config.ASR_LANGUAGE,
        beam_size=1,
        vad_filter=True,
    )
    return "".join(s.text for s in segments).strip()


_FASTER_MODEL = None

_PROVIDERS: dict[str, Callable[[np.ndarray], str]] = {
    "groq": _groq,
    "mlx": _mlx,
    "funasr": _funasr,
    "faster": _faster,
}


def detect_provider() -> str:
    """按优先级找出当前环境可用的 ASR 后端。"""
    if config.GROQ_API_KEY:
        return "groq"
    try:
        import mlx_whisper  # noqa: F401

        return "mlx"
    except ImportError:
        pass
    try:
        import funasr  # noqa: F401

        return "funasr"
    except ImportError:
        pass
    try:
        import faster_whisper  # noqa: F401

        return "faster"
    except ImportError:
        pass
    raise AsrUnavailable(
        "没有可用的语音识别后端。三选一：\n"
        "  · Mac 用户（推荐）：uv tool install sofa-coder-mcp --with mlx-whisper\n"
        "  · 白嫖云端：export GROQ_API_KEY=你的key（https://console.groq.com 免费申请）\n"
        "  · Windows/Linux：pip install \"sofa-coder-mcp[asr-faster]\"\n"
        "也可以用 SOFA_ASR=xxx 手动指定后端（groq/mlx/funasr/faster）。"
    )


def transcribe(pcm: np.ndarray) -> str:
    """把 16kHz int16 PCM 转成文字。"""
    if pcm is None or pcm.size == 0:
        return ""
    name = config.ASR_PROVIDER if config.ASR_PROVIDER != "auto" else detect_provider()
    if name not in _PROVIDERS:
        raise AsrUnavailable(f"未知 ASR 后端：{name}（可选 groq/mlx/funasr/faster）")
    text = _PROVIDERS[name](pcm)
    logger.info("[ASR·%s] %s", name, text)
    return text
