# Build context = repo root (path dep on packages/schemas/python)
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY packages/schemas/python packages/schemas/python
COPY services/realtime services/realtime
WORKDIR /app/services/realtime
RUN uv sync --frozen --no-dev
EXPOSE 8002
CMD ["uv", "run", "--no-sync", "uvicorn", "sitara_realtime.main:app", "--host", "0.0.0.0", "--port", "8002"]
