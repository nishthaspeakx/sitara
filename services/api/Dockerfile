# Build context = repo root (path dep on packages/schemas/python)
FROM python:3.12-slim
# Stamped by infra/dev-up.sh so a stale image is detectable
# rather than something you discover an hour into debugging.
ARG GIT_SHA="unknown"
LABEL org.sitara.git-sha=$GIT_SHA
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY packages/schemas/python packages/schemas/python
# The service renders §9's safety and decline strings itself, so the catalogs
# ship with it — `localisation.verify_catalogs` refuses to boot without them.
COPY packages/i18n/messages packages/i18n/messages
COPY packages/i18n/glossary.json packages/i18n/glossary.json
COPY services/api services/api
WORKDIR /app/services/api
RUN uv sync --frozen --no-dev
EXPOSE 8001
CMD ["uv", "run", "--no-sync", "uvicorn", "sitara_api.main:app", "--host", "0.0.0.0", "--port", "8001"]
