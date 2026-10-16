"""口语化清洗器测试：保证 TTS 永远不读出代码和路径。"""

from sofa_coder.cleaner import clean_for_speech
from sofa_coder.config import EXIT_PHRASE_RE


def test_fenced_code_block():
    out = clean_for_speech("我已经改好了：\n```python\nprint('hello')\n```\n编译没报错。")
    assert "print" not in out
    assert "一段" in out and "代码" in out
    assert "改好了" in out and "编译没报错" in out


def test_inline_path_code():
    out = clean_for_speech("我更新了 `src/App.vue` 里的样式。")
    assert "/" not in out.replace("，", "")  # 路径斜杠不应被读出来
    assert "App.vue" not in out
    assert "样式" in out


def test_short_inline_code_kept():
    out = clean_for_speech("把 `count` 加了 1。")
    assert "count" in out
    assert "`" not in out


def test_bare_unix_path():
    out = clean_for_speech("日志写在 /usr/local/bin/app 里了。")
    assert "/usr" not in out
    assert "本地路径" in out


def test_url_replaced():
    out = clean_for_speech("文档在 https://example.com/docs/quick-start 上。")
    assert "https://" not in out


def test_markdown_stripped():
    out = clean_for_speech("## 标题\n**重要**：*注意* 这一点。\n- 列表项")
    assert "#" not in out and "**" not in out
    assert "重要" in out and "注意" in out


def test_long_text_truncated_at_sentence():
    text = "第一句话。" * 60
    out = clean_for_speech(text, max_chars=50)
    assert len(out) <= 52
    assert out.endswith("。")


def test_empty_and_plain():
    assert clean_for_speech("") == ""
    assert clean_for_speech("搞定了。") == "搞定了。"


def test_exit_phrases():
    assert EXIT_PHRASE_RE.search("退下吧")
    assert EXIT_PHRASE_RE.search("好的，结束语音")
    assert EXIT_PHRASE_RE.search("我自己看一下")
    assert not EXIT_PHRASE_RE.search("帮我退出登录这个功能改一下")
