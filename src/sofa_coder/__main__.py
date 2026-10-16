"""sofa-coder 命令行入口。

    sofa-coder            # 默认：启动 MCP 服务器（stdio，给 Claude Code 等用）
    sofa-coder chat       # 终端语音自测：你说一句，它复述一句（调音频链路用）
    sofa-coder doctor     # 环境体检：麦克风/扬声器/VAD/ASR/TTS 逐项检查
    sofa-coder say <文本>  # 只测 TTS 播报
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def _cmd_server(_args: argparse.Namespace) -> int:
    from .server import run

    run()
    return 0


def _cmd_say(args: argparse.Namespace) -> int:
    from . import tts

    interrupted = tts.speak(args.text)
    print("（播报被你打断了）" if interrupted else "（播报完成）")
    return 0


def _cmd_chat(_args: argparse.Namespace) -> int:
    from . import asr, config, tts
    from .audio import play_chime
    from .vad import Ear, SileroVAD, listen_once

    print("🎧 语音自测模式：说一句话（停顿后发送），Ctrl-C 退出。")
    print(f"   断句停顿 {config.SILENCE_MS}ms · ASR 后端将自动探测\n")
    with Ear() as ear:
        vad = SileroVAD()
        while True:
            print("🎤 请说话……", flush=True)
            pcm = listen_once(ear, vad)
            if pcm is None:
                print("（没听到人声，再试一次）")
                continue
            play_chime("ack")
            try:
                text = asr.transcribe(pcm)
            except Exception as exc:
                print(f"❌ ASR 失败：{exc}")
                return 1
            print(f"📝 你说：{text}\n")
            if config.EXIT_PHRASE_RE.search(text):
                play_chime("bye")
                print("👋 检测到退出短语，自测结束。")
                return 0
            tts.speak(f"收到，你说的是：{text}")


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}" + (f" —— {detail}" if detail else ""))
    return ok


def _cmd_doctor(_args: argparse.Namespace) -> int:
    from . import config

    print("🩺 sofa-coder 环境体检\n")
    all_ok = True

    all_ok &= _check("Python 版本", sys.version_info >= (3, 10), sys.version.split()[0])

    # 依赖
    for mod, hint in [
        ("numpy", "pip install numpy"),
        ("sounddevice", "pip install sounddevice"),
        ("onnxruntime", "pip install onnxruntime"),
        ("miniaudio", "pip install miniaudio"),
        ("edge_tts", "pip install edge-tts"),
        ("fastmcp", "pip install fastmcp"),
    ]:
        try:
            __import__(mod)
            _check(f"依赖 {mod}", True)
        except ImportError:
            all_ok = False
            _check(f"依赖 {mod}", False, hint)

    if config.DRY_RUN:
        print("\n💤 SOFA_DRY_RUN=1，跳过所有音频设备检测。")
        return 0 if all_ok else 1

    # 输出设备
    try:
        import sounddevice as sd

        dev = sd.query_devices(None, "output")
        _check("扬声器/输出设备", True, f"{dev['name']} @{int(dev['default_samplerate'])}Hz")
    except Exception as exc:
        all_ok = False
        _check("扬声器/输出设备", False, str(exc))

    # 输入设备（macOS 首次会要麦克风权限）
    try:
        import sounddevice as sd

        dev = sd.query_devices(None, "input")
        _check("麦克风/输入设备", True, f"{dev['name']} @{int(dev['default_samplerate'])}Hz")
    except Exception as exc:
        all_ok = False
        _check(
            "麦克风/输入设备",
            False,
            f"{exc}（macOS 需在 系统设置→隐私与安全性→麦克风 里放行终端）",
        )

    # VAD 模型
    try:
        from .vad import SileroVAD

        SileroVAD()
        _check("Silero VAD", True, "模型就绪")
    except Exception as exc:
        all_ok = False
        _check("Silero VAD", False, str(exc))

    # ASR 后端
    try:
        from . import asr

        provider = asr.detect_provider()
        _check("ASR 语音识别", True, f"将使用 {provider}")
    except Exception as exc:
        all_ok = False
        _check("ASR 语音识别", False, str(exc))

    # TTS（edge-tts 需要联网）
    engines = []
    if config.TTS_ENGINE in ("auto", "edge"):
        engines.append("edge-tts（需联网）")
    if config.TTS_ENGINE in ("auto", "say") and config.IS_MAC:
        engines.append("macOS say（离线兜底）")
    print("  ℹ️ TTS 引擎链：" + " → ".join(engines))
    if config.TTS_ENGINE in ("auto", "edge"):
        try:
            import asyncio

            import edge_tts

            async def _probe() -> None:
                com = edge_tts.Communicate("测试", voice=config.TTS_VOICE)
                async for _ in com.stream():
                    break

            asyncio.run(asyncio.wait_for(_probe(), timeout=15))
            _check("edge-tts 连通性", True)
        except Exception as exc:
            print(f"  ⚠️ edge-tts 连不上（{exc}）；联网失败时会自动降级到系统 say。")

    print(
        "\n结果：" + ("全部就绪，躺平吧！🛋️" if all_ok else "有未通过的项，按上面提示修复即可。")
    )
    return 0 if all_ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sofa-coder",
        description="闭眼 Vibe Coding：静默改代码，张嘴说人话。",
    )
    parser.add_argument("--version", action="version", version=f"sofa-coder {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("server", help="启动 MCP 服务器（默认）")
    sub.add_parser("chat", help="终端语音自测：你说一句它复述一句")
    sub.add_parser("doctor", help="环境体检：麦克风/扬声器/VAD/ASR/TTS")
    p_say = sub.add_parser("say", help="只测语音播报")
    p_say.add_argument("text", help="要播报的文本")

    args = parser.parse_args(argv)
    cmd = args.cmd or "server"
    return {
        "server": _cmd_server,
        "chat": _cmd_chat,
        "doctor": _cmd_doctor,
        "say": _cmd_say,
    }[cmd](args)


if __name__ == "__main__":
    sys.exit(main())
