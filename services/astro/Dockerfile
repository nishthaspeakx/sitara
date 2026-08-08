# Build context = repo root (path dep on packages/schemas/python)
FROM python:3.12-slim
# Stamped by infra/dev-up.sh so a stale image is detectable
# rather than something you discover an hour into debugging.
ARG GIT_SHA="unknown"
LABEL org.sitara.git-sha=$GIT_SHA
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY packages/schemas/python packages/schemas/python
COPY services/astro services/astro
WORKDIR /app/services/astro
# pyswisseph ships no cp312 manylinux wheels — build it from source, then drop the toolchain
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && uv sync --frozen --no-dev \
    && apt-get purge -y build-essential && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
ENV SWISSEPH_DATA_PATH=/app/services/astro/data/swisseph
EXPOSE 8003
CMD ["uv", "run", "--no-sync", "uvicorn", "sitara_astro.main:app", "--host", "0.0.0.0", "--port", "8003"]
