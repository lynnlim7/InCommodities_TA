# Power Position Tool - Streamlit dashboard
#
# Two stages over one base image. The builder resolves dependencies from
# uv.lock; the runtime carries only the resulting virtualenv and the source.
# Both stages share the same base and the same /app path, so the virtualenv
# copied between them keeps working: uv writes absolute interpreter paths into
# it, and a different base would invalidate them.

FROM python:3.13-slim-bookworm AS builder

# Pinned so a rebuild resolves dependencies the same way months from now.
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, in their own layer: editing application code then costs a
# rebuild of only the final layer rather than a full reinstall.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# README.md is required because pyproject.toml declares it as the project
# readme, and the build backend reads it when installing the project itself.
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev


FROM python:3.13-slim-bookworm

# Streamlit writes runtime state under $HOME, so the app runs as a non-root
# user that owns a real home directory rather than writing into /.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8501

# Streamlit's own readiness endpoint. Probed with the stdlib so the image needs
# no curl or wget, and so `make run` can wait for "healthy" before opening a
# browser instead of racing the server's startup.
HEALTHCHECK --interval=3s --timeout=3s --start-period=5s --retries=20 \
    CMD ["python", "-c", "import sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2).status == 200 else 1)"]

# address 0.0.0.0 is what makes the server reachable from the host; the default
# binds inside the container only. headless stops Streamlit trying to open a
# browser in a container that has none - the host opens it instead.
CMD ["streamlit", "run", "src/app/dashboard/main.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
