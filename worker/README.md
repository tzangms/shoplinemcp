# shopline MCP — Cloudflare Python Worker

把 `shopline_mcp` 的 MCP 工具與多店 middleware 部署成 Cloudflare Python Worker（stateless streamable-http），
取代 Zeabur 的長駐版（`shopline_mcp/remote.py`）。工具定義與 `MultiStoreKeyMiddleware` 共用，本目錄只是部署殼。

連接器網址：`https://shopline-mcp.<subdomain>.workers.dev/<STORE_KEY>/mcp`（每個店家一組密鑰）

## 部署

需要 [uv](https://docs.astral.sh/uv/)（≥ 0.12.3）與已登入的 wrangler（`npx wrangler login`）。

```bash
cd worker
uvx --from workers-py pywrangler deploy --dry-run --outdir dist   # 先看打包大小
uvx --from workers-py pywrangler deploy

# secrets：每個店家一組 KEY/TOKEN（label 自訂，例 A、B）
npx wrangler secret put SHOPLINE_STORE_A_KEY
npx wrangler secret put SHOPLINE_STORE_A_TOKEN
```

本機測試：把上述變數寫進 `worker/.dev.vars`（已 gitignore），`uvx --from workers-py pywrangler dev`。

## 打包大小（免費方案 gzip 上限 3 MB）

目前約 2.9 MB，餘裕很小。為了塞進免費方案：

- `pyproject.toml` 用 `override-dependencies` 拿掉 server 用不到的 `pyjwt[crypto]`/`cryptography`、
  `charset-normalizer`、`python-multipart`、`typer`（`mcp[cli]` 帶進來的）
- `wrangler.jsonc` 的 `python_modules.exclude` 排除 `.pyc`/`.pyi`/授權檔、`pydantic.v1`、`mcp/cli`
- `pylock.toml` 有進版控，鎖住相依版本；升級 `mcp` 或加相依後請先跑 `--dry-run` 確認大小

超過 3 MB 或遇到 CPU 超時（錯誤 1102，免費方案每 request 10 ms CPU；大量訂單查詢較容易撞到）
就改用 Workers Paid（$5/月）。

## 與 Zeabur 版的差異

- Workers 每個 request 跑一次，無法長駐 uvicorn：`src/entry.py` 每個 request 建 stateless session manager
- `remote.py` 頂層 `import uvicorn`，Pyodide 沒有 uvicorn，entry 先塞空 stub
- Worker secrets 要對底層 JS env（`self.env._env`）取 `Object.keys` 才列得出來，
  再灌進 `os.environ` 給 `build_stores()` 用
- 同步的 `requests` 可用（Pyodide 的 urllib3 走 JSPI fetch），tools 不用改
