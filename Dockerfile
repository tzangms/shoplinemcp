FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir ".[remote]"

# Zeabur 會以 PORT 環境變數指定實際埠號
ENV MCP_TRANSPORT=http \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

CMD ["shopline-mcp"]
