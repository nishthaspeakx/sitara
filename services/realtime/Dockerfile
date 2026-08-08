# Build context = repo root (path dep on packages/schemas/python)
FROM python:3.12-slim
# Stamped by infra/dev-up.sh so a stale image is detectable
# rather than something you discover an hour into debugging.
ARG GIT_SHA="unknown"
LABEL org.sitara.git-sha=$GIT_SHA
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY packages/schemas/python packages/schemas/python
COPY services/realtime services/realtime
WORKDIR /app/services/realtime
RUN uv sync --frozen --no-dev
EXPOSE 8002
CMD ["uv", "run", "--no-sync", "uvicorn", "sitara_realtime.main:app", "--host", "0.0.0.0", "--port", "8002"]
