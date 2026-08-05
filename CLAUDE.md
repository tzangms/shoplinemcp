# shopline-mcp

## Zeabur Deployment (remote HTTP MCP)

- Project ID: `6a1fa6dc96bc20746b5064fe`（與 Flaps 同一 project）
- Service ID: `6a732f6ec9628aefeeec6c53`（service 名稱 `shopline-mcp`）
- Environment ID: `6a1fa6dc95b39806d284a2d0`
- Domain: `shopline-mcp.zeabur.app`
- Start command（zbpack.json）: `python -m shopline_mcp.remote`

### 環境變數
- `SHOPLINE_MCP_KEY` — URL 路徑密鑰（連接器門鎖）
- `SHOPLINE_API_TOKEN` — Shopline Open API token（店家資料鑰匙；由後台 Settings → Staff Settings → API Auth 產生）
- `PORT` — 已設為 `${WEB_PORT}`（Zeabur 自動注入）

### Claude 自訂連接器網址
`https://shopline-mcp.zeabur.app/<SHOPLINE_MCP_KEY>/mcp`

### 重新部署（更新程式碼，務必帶 --service-id 避免建立重複 service）
```bash
npx zeabur@latest deploy --project-id 6a1fa6dc96bc20746b5064fe --service-id 6a732f6ec9628aefeeec6c53 --json
```
