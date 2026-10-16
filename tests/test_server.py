"""dry-run 全链路测试：SOFA_DRY_RUN=1 时不碰任何真实音频设备。"""

import pytest

from fastmcp import Client

from sofa_coder import config


@pytest.fixture()
def dry_run(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", True)
    monkeypatch.setattr(config, "DRY_RUN_REPLY", "帮我把标题栏改成渐变色")


def _text(result) -> str:
    return result.content[0].text


@pytest.mark.anyio
async def test_vibe_notify_dry(dry_run):
    from sofa_coder.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("vibe_notify", {"text": "我先去跑个构建 **--verbose**，路径在 /usr/bin/x"})
        assert "已播报" in _text(result)


@pytest.mark.anyio
async def test_vibe_talk_dry_returns_instruction(dry_run):
    from sofa_coder.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("vibe_talk", {"spoken_summary": "搞定啦 ```python\nx=1\n```"})
        out = _text(result)
        assert "[用户语音指令]:" in out
        assert "帮我把标题栏改成渐变色" in out
        assert "再次调用 vibe_talk" in out


@pytest.mark.anyio
async def test_vibe_talk_broadcast_only(dry_run):
    from sofa_coder.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool(
            "vibe_talk", {"spoken_summary": "好了", "wait_for_reply": False}
        )
        assert "已播报" in _text(result)


@pytest.mark.anyio
async def test_tools_registered():
    from sofa_coder.server import mcp

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}
    assert tools == {"vibe_talk", "vibe_notify"}
