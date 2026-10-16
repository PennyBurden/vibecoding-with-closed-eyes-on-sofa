"""会话编排：把 清洗 → TTS 播报（可打断）→ 提示音 → VAD 倾听 → ASR 串成闭环。

MCP 工具只做薄封装，真正的流程在这里：
  vibe_talk(summary) = 播报上一步结果 + 倾听下一条指令（阻塞式）
  vibe_notify(text)  = 耗时任务前的非阻塞过渡语
"""

from __future__ import annotations

import logging
import threading

from . import asr, config, tts
from .audio import BargeWatcher, play_chime
from .cleaner import clean_for_speech
from .vad import Ear, SileroVAD

logger = logging.getLogger("sofa-coder")

# MCP 工具可能被并发调用，而麦克风/扬声器是独占资源，必须串行化
_audio_lock = threading.Lock()

_EXIT_ACK = "好嘞，那我就闭嘴了，屏幕前见。"


def _listen_with_retry(ear: Ear, vad: SileroVAD) -> tuple:
    """听一次，超时没人说话则轻声再催一次。返回 (pcm, timed_out)。"""
    pcm = None
    for attempt in range(2):
        pcm = None
        try:
            from .vad import listen_once

            pcm = listen_once(ear, vad)
        except Exception as exc:
            logger.exception("倾听失败：%s", exc)
            return None, True
        if pcm is not None:
            return pcm, False
        if attempt == 0:
            play_chime("ding")  # 轻轻催一下
    return None, True


def vibe_talk(spoken_summary: str, wait_for_reply: bool = True) -> str:
    """向用户播报执行结果，然后（可选）张嘴听下一条指令。

    返回带前缀标记的文本，让大模型明确知道下一步该干嘛。
    """
    try:
        return _vibe_talk_impl(spoken_summary, wait_for_reply)
    except Exception as exc:  # 语音链路任何环节崩了都不能让 Agent 卡死
        logger.exception("vibe_talk 语音链路出错")
        return (
            f"[语音系统出错]: {exc}\n"
            "请改为普通文本回复用户，并建议其在终端运行 `sofa-coder doctor` 排查环境。"
        )


def _vibe_talk_impl(spoken_summary: str, wait_for_reply: bool) -> str:
    with _audio_lock:
        speech = clean_for_speech(spoken_summary)
        if not speech:
            speech = "这步搞定了。"

        if config.DRY_RUN:
            logger.info("[vibe_talk·dry] 播报：%s", speech)
            if not wait_for_reply:
                return "已播报（dry-run），未等待回复。"
            reply = config.DRY_RUN_REPLY
            return _wrap_reply(reply)

        interrupted = False
        ear = None
        use_barge = config.BARGE_IN
        try:
            if use_barge:
                from .vad import SileroVAD

                ear = Ear().__enter__()
                vad = SileroVAD()
                watcher = BargeWatcher(ear, vad)
                ear.drain()  # 播报前的残留声音不算数
                interrupted = tts.speak(speech, watcher)
                if not interrupted:
                    watcher.triggered = False  # 重置，播报后继续用耳朵等插话
            else:
                tts.speak(speech)

            if not wait_for_reply:
                if interrupted:
                    return "播报被用户插话打断了：用户可能迫不及待想说需求，但这次无法听到内容，请在下次 vibe_talk 时播报更简短。"
                return "已播报完毕，未等待回复。可以继续干活，干完再调用 vibe_talk。"

            if not interrupted and config.SOUND:
                play_chime("ding")  # 叮：请说话
            if ear is None:
                from .vad import Ear as _Ear, SileroVAD as _VAD

                ear = _Ear().__enter__()
                vad = _VAD()
            ear.drain()

            pcm, timed_out = _listen_with_retry(ear, vad)
            if config.SOUND:
                play_chime("ack")  # 咚：收到，开干
            if pcm is None or timed_out:
                return config.NO_SPEECH_HINT

            text = asr.transcribe(pcm).strip()
            if not text:
                return config.UNCLEAR_HINT
            if config.EXIT_PHRASE_RE.search(text):
                if config.SOUND:
                    play_chime("bye")
                return (
                    f"[用户要求结束语音模式] 用户原话：{text}\n"
                    "请用一句大白话做收尾确认，之后不要再调用 vibe_talk / vibe_notify，"
                    "改为普通文本回复。"
                )
            return _wrap_reply(text)
        finally:
            if ear is not None:
                try:
                    ear.__exit__(None, None, None)
                except Exception:  # noqa: S110
                    pass


def _wrap_reply(text: str) -> str:
    return (
        f"[用户语音指令]: {text}\n"
        "（请立刻继续执行；完成一个闭环后再次调用 vibe_talk 汇报。"
        "记住：汇报必须是两句以内的口语，禁止出现代码块、文件路径和 Markdown。）"
    )


def vibe_notify(text: str) -> str:
    """非阻塞过渡语：耗时任务开跑前先吭一声，让用户安心闭眼。"""
    with _audio_lock:
        speech = clean_for_speech(text)
        if not speech:
            return "内容为空，没有播报。"
        if config.DRY_RUN:
            logger.info("[vibe_notify·dry] 播报：%s", speech)
            return "已播报（dry-run）。"
        tts.speak(speech)
        return "已播报完毕。可以继续干活了。"
