import asyncio

from live_read_tools import mcp, readonly_tool_names


def test_every_tool_annotated_by_write_calls():
    # 以 live_read_tools 的 AST 判定為準：放錯目錄的寫入工具也會被抓出來
    readonly = readonly_tool_names()
    tools = asyncio.run(mcp.list_tools())
    assert tools
    for t in tools:
        ann = t.annotations
        assert ann is not None, t.name
        if t.name in readonly:
            assert ann.readOnlyHint is True, t.name
            assert not ann.destructiveHint, t.name
        else:
            assert ann.readOnlyHint is False, t.name
            assert ann.destructiveHint is True, t.name
