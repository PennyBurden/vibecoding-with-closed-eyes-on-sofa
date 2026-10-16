<div align="center">

<img src="assets/banner.svg" alt="sofa-coder：闭眼 Vibe Coding" width="880"/>

# sofa-coder 🛋️

**闭眼 Vibe Coding（躺平当甲方模式）**

> **静默改代码，张嘴说人话。**
> Stop staring at diffs. Close your eyes, lean back, and vibe-code like a tech lead on a phone call.

[![CI](https://github.com/PennyBurden/vibecoding-with-closed-eyes-on-sofa/actions/workflows/ci.yml/badge.svg)](https://github.com/PennyBurden/vibecoding-with-closed-eyes-on-sofa/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sofa-coder-mcp)](https://pypi.org/project/sofa-coder-mcp/)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

戴上耳机、闭眼躺沙发。像跟技术合伙人打电话一样把需求聊完，Agent 在后台自己改代码、跑测试、修 Bug，最后只用一两句大白话汇报。你看都不用看屏幕一眼。

现有的语音编程工具大多死在两件事上：要么让你**用嘴念语法**（"右括号分号"，念到怀疑人生），要么把 **500 行报错和 Diff 一字不落读给你听**（听到脑壳疼）。sofa-coder 反过来：Agent 在终端静默干活，只跟你聊人话。

---

## ✨ 它解决了"闭眼"的三大盲区

| 盲区 | sofa-coder 的答案 |
| --- | --- |
| "它死机了吗？" | **听觉心跳**：耗时操作前自动过渡语（"我先跑个构建，稍等哈"）+ 轻 提示音 |
| "它现在在干嘛？" | **口语化压缩播报**：内置清洗器把代码块/路径/Markdown 全部过滤，只播 ≤2 句大白话；严禁读代码 |
| "弹窗卡住怎么办？" | **全语音权限审批**：删文件/装依赖/跑迁移自动拦截，语音问一句"搞吗？"，你说"搞"就放行 |

外加两个基础体验：**免按键连续对话**（Silero VAD 自动断句，停顿 1.5s 自动发送，彻底告别按住空格说话）和 **Barge-in 打断**（它废话太多时你直接开口，它立刻闭嘴听你说）。

<!-- TODO: 首屏演示 GIF（建议分屏实拍：左边真人躺沙发闭眼说话，右边屏幕加速回放）
![demo](docs/demo.gif)
-->

## 🚀 30 秒接入 Claude Code

```bash
# 方案 A · Mac 用户推荐（本地 mlx-whisper，无需任何 API Key）
claude mcp add sofa-coder -- uvx --from "sofa-coder-mcp[asr-mlx]" sofa-coder

# 方案 B · 白嫖云端（免费 Groq API Key，任何平台，速度飞快）
export GROQ_API_KEY=你的key   # https://console.groq.com 免费申请
claude mcp add sofa-coder -- uvx sofa-coder-mcp

# 方案 C · Windows / Linux（本地 faster-whisper）
claude mcp add sofa-coder -- uvx --from "sofa-coder-mcp[asr-faster]" sofa-coder
```

重启 Claude Code，然后对它说：

> **「进入闭眼模式。帮我写个复古贪吃蛇网页，背景要黑客帝国那种代码雨。」**

然后就可以把笔记本推到一边，闭眼听它干活了。说「退下吧」结束语音模式。

### Cursor / Windsurf / Cline 等其他 MCP 宿主

在 MCP 配置 JSON 里加：

```json
{
  "mcpServers": {
    "sofa-coder": {
      "command": "uvx",
      "args": ["--from", "sofa-coder-mcp[asr-mlx]", "sofa-coder"]
    }
  }
}
```

### Claude Code Skill 形态（推荐搭配使用）

MCP 提供耳朵和嘴巴，Skill 提供大脑的行为铁律。把本仓库的
[SKILL.md](SKILL.md) 装进技能目录即可：

```bash
git clone https://github.com/PennyBurden/vibecoding-with-closed-eyes-on-sofa.git
mkdir -p ~/.claude/skills/sofa-coder
cp vibecoding-with-closed-eyes-on-sofa/SKILL.md ~/.claude/skills/sofa-coder/SKILL.md
```

## 🩺 跑不通？先体检

```bash
uvx sofa-coder-mcp doctor    # 麦克风/扬声器/VAD/ASR/TTS 逐项检查
uvx sofa-coder-mcp chat      # 终端语音自测：你说一句它复述一句
uvx sofa-coder-mcp say 你好  # 只测播报
```

macOS 记得在 **系统设置 → 隐私与安全性 → 麦克风** 里给终端放行。

## ⚙️ 配置（全可选项，不改就是零成本默认）

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `SOFA_ASR` | `auto` | 语音识别后端：`auto` / `groq` / `mlx` / `funasr` / `faster` |
| `GROQ_API_KEY` | 无 | 配了就自动优先用 Groq 云端识别 |
| `SOFA_TTS_VOICE` | `zh-CN-XiaoxiaoNeural` | Edge-TTS 音色（男声可用 `zh-CN-YunxiNeural`） |
| `SOFA_TTS` | `auto` | `edge`（联网、音色好）/ `say`（macOS 离线兜底）/ `off` |
| `SOFA_SILENCE_MS` | `1500` | 停顿多久算一句话说完 |
| `SOFA_BARGE_IN` | `on` | 播报中被你插话是否立即闭嘴（外放扬声器易误触发，戴耳机体验最佳） |
| `SOFA_SOUND` | `on` | 叮/咚提示音 |
| `SOFA_MAX_UTTERANCE_S` | `30` | 单次发言上限 |

## 🔌 MCP 工具（就 2 个，驱动整个闭环）

| 工具 | 作用 |
| --- | --- |
| `vibe_talk(spoken_summary, wait_for_reply=True)` | 阻塞式：播报大白话 → 叮一声 → 听用户说 → 返回 `[用户语音指令]: …`。大模型靠它进入无限对话流 |
| `vibe_notify(text)` | 非阻塞过渡语："我去跑个构建，稍等哈"。让闭眼用户安心 |

`vibe_talk` 的 docstring 里写死了铁律（禁止代码块/路径/Markdown、2 句话以内、高危操作先审批），返回值里也带行动指令，双保险让模型守规矩。即使 LLM 脑抽输出了 ` ```python ` 或 `/usr/local/bin`，内置清洗器也会在 TTS 之前替换成「一段代码」「本地路径」。

## 🧱 技术架构（零配置开箱 + 进阶可选）

| 模块 | 默认（0 成本） | 进阶（可选） |
| --- | --- | --- |
| 宿主接入 | FastMCP（stdio）+ SKILL.md | 任意支持 MCP 的宿主 |
| 断句 | Silero VAD（ONNX，无需 PyTorch，模型仅 2MB 首次自动下载） | — |
| 语音识别 | mlx-whisper（Mac）/ faster-whisper（Win/Linux）/ Groq 云端 | FunASR SenseVoiceSmall（中英混杂最佳） |
| 语音播报 | Edge-TTS（晓晓/云希，免 Key） | macOS `say` 离线零延迟兜底 |
| 音频 | sounddevice + miniaudio（无 ffmpeg 依赖） | — |

### 痛点对比

| | 传统语音输入法 | 普通 TTS 插件 | sofa-coder |
| --- | --- | --- | --- |
| 你要干嘛 | 用嘴念语法和标点 | 被动听 Agent 读 Diff 和报错 | 像打电话一样聊需求 |
| 说一句话的成本 | "反引号 src 斜杠…" 😵 | 无需说话 🎧 | 张嘴就行 🛋️ |
| 听到什么 | 自己的语法 | 500 行报错 | "修好啦，编译没报错" |
| 断句 | 手动按键 | — | VAD 自动断句 + 插话打断 |

## 🗺️ Roadmap

- [ ] 唤醒词模式（"嘿 小沙发"，彻底解放双手）
- [ ] WebRTC VAD 备选与回声消除，优化外放场景的打断体验
- [ ] Kokoro-82M 本地高音质 TTS
- [ ] 多语言支持（English voice loop）
- [ ] 情绪识别：检测到用户烦躁时自动放慢节奏、增加确认

## 🎬 帮我们点个 Star（以及拍个视频）

如果你也瘫在沙发上用它写完了个项目，欢迎提 issue 分享截图；拍分屏演示视频（左边你躺平说话、右边屏幕加速）@ 我们，最好的视频会放进 README。

欢迎 PR！口号：**让所有人都能躺着当甲方。**

## License

[MIT](LICENSE)
