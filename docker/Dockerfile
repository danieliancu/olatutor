FROM python:3.13-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --root-user-action=ignore uv==0.13.6

WORKDIR /app
COPY pyproject.toml uv.lock ./

FROM base AS dev
RUN uv sync --frozen --no-cache
RUN useradd --create-home --uid 1000 app
USER app
COPY --chown=app:app . /app

FROM base AS e2e
RUN uv sync --frozen --no-cache --group e2e
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN playwright install --with-deps chromium firefox webkit
COPY . /app
