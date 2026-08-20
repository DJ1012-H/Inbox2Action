FROM ghcr.io/astral-sh/uv:0.8.17-python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install from the frozen lock before copying source for a cacheable build.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY db ./db
COPY scripts ./scripts
COPY src ./src

RUN uv sync --frozen --no-dev \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin inbox2action

USER inbox2action

EXPOSE 8080

ENTRYPOINT ["uv", "run", "--frozen", "python"]
