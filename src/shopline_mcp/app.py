"""Shopline MCP app instance — shared FastMCP singleton."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("shopline")

# client（如 Claude）依 annotations 決定哪些工具要先跟使用者確認。
READ_ONLY = ToolAnnotations(readOnlyHint=True)
# tools/writes/ 下的工具都會改動正式商店資料（含刪除、取消訂單、發券），一律標 destructive。
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)
