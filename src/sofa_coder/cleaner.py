"""口语化清洗器：把大模型可能输出的"机器味"文本洗成适合朗读的人话。

万一 LLM 脑抽输出了 ```python、/usr/local/bin、Markdown 表格，
在送入 TTS 之前在这里统一过滤成「一段代码」「本地路径」这类口语替代。
"""

from __future__ import annotations

import re

# 各种"机器味"及其口语替代
_FENCED_CODE_RE = re.compile(r"```[\w+-]*[^\S\n]*\n.*?```", re.DOTALL)
_FENCED_CODE_LANG_RE = re.compile(r"^```([\w+-]+)", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_URL_RE = re.compile(r"https?://\S+")
_UNIX_PATH_RE = re.compile(r"(?:/[\w.\-@+]+){2,}")                      # /usr/local/bin
_WIN_PATH_RE = re.compile(r"[A-Za-z]:\\(?:[\w.\- ]+\\?)+")               # C:\Users\foo
_REL_PATH_RE = re.compile(
    r"(?:\.{1,2}/)?[\w\-]+(?:/[\w.\-]+)+\.(?:py|js|jsx|ts|tsx|vue|json|md|html?"
    r"|css|scss|less|yaml|yml|toml|sh|bash|zsh|rs|go|java|kt|swift|c|cpp|h|hpp"
    r"|cs|rb|php|sql|lock|env|gitignore)\b",
    re.IGNORECASE,
)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_MD_ITALIC_RE = re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])|(?<![\w_])_([^_\n]+)_(?![\w_])")
_MD_HEADER_RE = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_MD_QUOTE_RE = re.compile(r"^\s*>\s?", re.MULTILINE)
_MD_HR_RE = re.compile(r"^\s*[-*_]{3,}\s*$", re.MULTILINE)
_MD_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", re.MULTILINE)
_MD_PIPES_RE = re.compile(r"\s*\|\s*")
_MD_LIST_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_DIFF_LINES_RE = re.compile(r"^[+-]{3,}.*$", re.MULTILINE)
_MULTI_BLANK_RE = re.compile(r"\n\s*\n+")
_MULTI_SPACE_RE = re.compile(r"[^\S\n]+")
_MULTI_PUNCT_RE = re.compile(r"([。！？；：,.!?;:])\1+")
_SENTENCE_END_RE = re.compile(r"[。！？!?…]")

# 口语替代词的少量变体，避免每次播报一字不差（用文本长度取模做确定性选择）
_CODE_ALIASES = ["一段代码", "一小段代码"]
_PATH_ALIASES = ["本地路径", "一个本地路径"]
_URL_ALIASES = ["一个网页链接", "一个链接"]

# 最终硬上限：超长就按句子边界截断
MAX_SPEECH_CHARS = 160


def _pick(aliases: list[str], seed: int) -> str:
    return aliases[seed % len(aliases)]


def _is_path_like(text: str) -> bool:
    return bool(
        _UNIX_PATH_RE.search(text)
        or _WIN_PATH_RE.search(text)
        or _REL_PATH_RE.search(text)
        or re.search(r"\.\w{1,6}$", text.strip())  # 以扩展名结尾，比如 App.vue
    )


def clean_for_speech(text: str, max_chars: int = MAX_SPEECH_CHARS) -> str:
    """把任意 LLM 输出清洗成适合 TTS 朗读的短人话。"""
    if not text:
        return ""
    seed = len(text)

    # 1. 围栏代码块 → 一段代码
    def _fenced(m: re.Match) -> str:
        lang = _FENCED_CODE_LANG_RE.match(m.group(0))
        if lang and lang.group(1).lower() in ("python", "py"):
            return "一段 Python 代码"
        return _pick(_CODE_ALIASES, seed)

    out = _FENCED_CODE_RE.sub(_fenced, text)

    # 2. 行内代码：路径类 → 本地路径，其余去掉反引号保留内容
    def _inline(m: re.Match) -> str:
        inner = m.group(1).strip()
        if not inner:
            return ""
        if _is_path_like(inner):
            return _pick(_PATH_ALIASES, seed)
        return inner

    out = _INLINE_CODE_RE.sub(_inline, out)

    # 3. 裸路径 / URL
    out = _URL_RE.sub(_pick(_URL_ALIASES, seed), out)
    out = _WIN_PATH_RE.sub(_pick(_PATH_ALIASES, seed), out)
    out = _UNIX_PATH_RE.sub(_pick(_PATH_ALIASES, seed), out)
    out = _REL_PATH_RE.sub("本地文件", out)

    # 4. Markdown 修饰全部剥掉
    out = _MD_LINK_RE.sub(r"\1", out)
    out = _MD_BOLD_RE.sub(lambda m: m.group(1) or m.group(2) or "", out)
    out = _MD_ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or "", out)
    out = _MD_HEADER_RE.sub("", out)
    out = _MD_QUOTE_RE.sub("", out)
    out = _MD_HR_RE.sub(" ", out)
    out = _MD_TABLE_SEP_RE.sub(" ", out)
    out = _MD_PIPES_RE.sub("，", out)
    out = _MD_LIST_RE.sub("", out)
    out = _DIFF_LINES_RE.sub("", out)

    # 5. 掉不认识的花哨符号，合并空白
    out = out.replace("`", "").replace("```", "")
    out = _MULTI_BLANK_RE.sub("。", out)
    out = _MULTI_SPACE_RE.sub(" ", out)
    out = out.replace("\n", "。")
    out = _MULTI_PUNCT_RE.sub(r"\1", out)
    out = re.sub(r"\s*。\s*", "。", out).strip().lstrip("。，, ").rstrip("，, 、")

    # 保证有个像样的收尾句读，TTS 朗读会有自然的降调
    if out and out[-1] not in "。！？!?…；：":
        out += "。"

    # 6. 超长截断：按句子边界切
    if len(out) > max_chars:
        cut = out[:max_chars]
        ends = [m.end() for m in _SENTENCE_END_RE.finditer(cut)]
        if ends:
            out = cut[: ends[-1]]
        else:
            out = cut.rstrip() + "……"
    return out.strip()
