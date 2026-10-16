"""集中管理所有环境变量配置。

设计原则：全部可选、默认零成本开箱。用户不改任何配置就应该能跑；
进阶用户通过环境变量切换 ASR / TTS 后端。
"""

from __future__ import annotations

import os
import pathlib
import re
import sys


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "y")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

# --- 运行模式 ---------------------------------------------------------------
# SOFA_DRY_RUN=1 时不碰任何音频设备：TTS 打印到 stderr、麦克风返回预设文本。
# 供 CI / 无声环境自测使用。
DRY_RUN = _env_bool("SOFA_DRY_RUN", False)
DRY_RUN_REPLY = os.environ.get("SOFA_DRYRUN_REPLY", "帮我把标题栏改成渐变色")

# --- 音频参数 ---------------------------------------------------------------
SAMPLE_RATE = 16000          # Silero VAD 与大多数 ASR 的标准采样率
FRAME_SAMPLES = 512          # VAD 每帧样本数（16kHz 下约 32ms）
SILENCE_MS = _env_int("SOFA_SILENCE_MS", 1500)        # 停顿多久算说完
MAX_UTTERANCE_S = _env_float("SOFA_MAX_UTTERANCE_S", 30.0)  # 单次发言上限
FIRST_REPLY_TIMEOUT_S = _env_float("SOFA_FIRST_REPLY_TIMEOUT_S", 8.0)  # 等用户开口的时限
BARGE_IN = _env_bool("SOFA_BARGE_IN", True)  # 播报中用户开口是否立即闭嘴
SOUND = _env_bool("SOFA_SOUND", True)        # 提示音（叮/咚）
VAD_THRESHOLD = _env_float("SOFA_VAD_THRESHOLD", 0.5)
BARGE_IN_THRESHOLD = _env_float("SOFA_BARGE_IN_THRESHOLD", 0.78)  # 比正常判定更严，防扬声器回声误触发

# --- TTS -------------------------------------------------------------------
# SOFA_TTS: auto | edge | say | off
TTS_ENGINE = os.environ.get("SOFA_TTS", "auto").strip().lower()
TTS_VOICE = os.environ.get("SOFA_TTS_VOICE", "zh-CN-XiaoxiaoNeural")
MAC_SAY_VOICE = os.environ.get("SOFA_MAC_SAY_VOICE", "Tingting")

# --- ASR -------------------------------------------------------------------
# SOFA_ASR: auto | groq | mlx | funasr | faster
ASR_PROVIDER = os.environ.get("SOFA_ASR", "auto").strip().lower()
ASR_LANGUAGE = os.environ.get("SOFA_ASR_LANGUAGE", "auto")  # auto/zh/en...
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("SOFA_GROQ_MODEL", "whisper-large-v3-turbo")
GROQ_BASE_URL = os.environ.get("SOFA_GROQ_BASE_URL", "https://api.groq.com/openai/v1")
FUNASR_MODEL = os.environ.get("SOFA_FUNASR_MODEL", "iic/SenseVoiceSmall")
FASTER_WHISPER_MODEL = os.environ.get("SOFA_FASTER_MODEL", "small")
MLX_WHISPER_MODEL = os.environ.get("SOFA_MLX_MODEL", "mlx-community/whisper-small")

# --- VAD 模型 ---------------------------------------------------------------
CACHE_DIR = pathlib.Path(
    os.environ.get("SOFA_CACHE_DIR", str(pathlib.Path.home() / ".cache" / "sofa-coder"))
)
VAD_MODEL_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
)

# --- 口语化退出短语 ----------------------------------------------------------
EXIT_PHRASE_RE = re.compile(
    r"退下|结束语音|退出语音|关闭语音|停止语音|我自己看|我自己来|睁眼|撒退|散了吧"
)

# 用户长时间没说话时返回给大模型的提示
NO_SPEECH_HINT = (
    "[用户没有说话]: 可能用户已经离开或闭嘴休息了。"
    "如果你还有没汇报完的活，继续干；干完后再调用一次 vibe_talk 简短问候；"
    "若连续两次都没人应答，请用一句话收尾并停止调用语音工具。"
)
UNCLEAR_HINT = (
    "[没听清]: 用户可能声音太小或环境太吵，"
    "请调用 vibe_talk 用一句大白话请用户再说一遍。"
)


def vad_model_path() -> pathlib.Path:
    """Silero VAD ONNX 模型的本地缓存路径（首次使用时自动下载）。"""
    return CACHE_DIR / "silero_vad.onnx"
