"""sofa-coder MCP 服务器：只暴露两个工具，驱动"闭眼语音"闭环。

接入方式：
    claude mcp add sofa-coder -- uvx sofa-coder-mcp
"""

from __future__ import annotations

from fastmcp import FastMCP

from . import __version__, session

mcp = FastMCP(
    "sofa-coder",
    instructions=(
        "闭眼 Vibe Coding 语音桥：进入语音模式后，你的每一次对外汇报都必须通过 "
        "vibe_talk 工具（播报大白话 + 等待用户语音指令），耗时任务开跑前用 "
        "vibe_notify 过渡。严禁在传给这两个工具的文本里出现代码块、文件路径、"
        "行号或 Markdown 格式。用户说「退下吧 / 结束语音 / 我自己看」即退出语音模式。"
    ),
)


@mcp.tool(
    annotations={
        "title": "语音播报并等待用户指令",
        "readOnlyHint": False,
    }
)
def vibe_talk(spoken_summary: str, wait_for_reply: bool = True) -> str:
    """向用户语音播报执行结果，播完自动张开麦克风等下一条语音指令并返回文字。

    使用铁律（违反会毁掉"闭眼体验"）：
    1. spoken_summary 必须像朋友聊天：控制在 2 句话、50 字以内；
    2. 严禁出现代码块、文件路径、行号、Markdown 符号或连续英文术语——
       想说 src/App.vue 就说「入口组件」，想说报错栈就说「报了个错已修好」；
    3. 每完成一个任务闭环必须调用本工具汇报，不要连干多件事不吭声；
    4. 涉及删除文件、安装依赖、数据库迁移等高危操作时，先用本工具口语化提问，
       等用户回复"搞/可以/算了"再动手；
    5. 若返回内容以 [用户要求结束语音模式] 开头，请一句话收尾，此后不再调用语音工具。

    Args:
        spoken_summary: 要播报的大白话（≤2 句，禁止代码/路径/Markdown）。
        wait_for_reply: 播报后是否等待并返回用户的下一条语音指令（默认 true）。
    """
    return session.vibe_talk(spoken_summary, wait_for_reply=wait_for_reply)


@mcp.tool(
    annotations={
        "title": "语音过渡语（不等待）",
        "readOnlyHint": False,
    }
)
def vibe_notify(text: str) -> str:
    """非阻塞地播报一句过渡语（不等待回复），让闭眼的用户知道你没死机。

    什么时候用：即将执行超过 10 秒的耗时操作（跑构建/装依赖/跑测试/大范围重构）之前，
    先吭一声，例如「我先去跑个构建，稍等哈」。同样禁止代码块、路径和 Markdown。

    Args:
        text: 要播报的大白话过渡语（1 句话以内）。
    """
    return session.vibe_notify(text)


def run() -> None:
    """以 stdio 方式启动 MCP 服务器。"""
    mcp.run()


if __name__ == "__main__":
    run()

__all__ = ["mcp", "run", "__version__"]
