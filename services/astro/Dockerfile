# Build context = repo root (path dep on packages/schemas/python)
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY packages/schemas/python packages/schemas/python
COPY services/astro services/astro
WORKDIR /app/services/astro
RUN uv sync --frozen --no-dev
EXPOSE 8003
CMD ["uv", "run", "--no-sync", "uvicorn", "sitara_astro.main:app", "--host", "0.0.0.0", "--port", "8003"]
