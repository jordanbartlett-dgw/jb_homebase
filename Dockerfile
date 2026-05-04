FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ src/
COPY evals/ evals/
COPY scripts/ scripts/

# Install dependencies and the project itself
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "jordan_claw.main:app", "--host", "0.0.0.0", "--port", "8000"]
