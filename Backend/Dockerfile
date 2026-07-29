FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

FROM base AS builder
COPY pyproject.toml ./
# The image serves the FastAPI app (see CMD), so it needs the `server` extra —
# plain `pip install .` is the lean agent-only install.
RUN pip install --upgrade pip && pip install ".[server]"

FROM base AS runtime
RUN useradd -m -u 10001 app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY app/ ./app/
COPY pyproject.toml ./
RUN mkdir -p /app/artifacts && chown -R app:app /app
USER app
EXPOSE 8000 7860 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys;\
import urllib.request as u; \
u.urlopen('http://localhost:8000/readyz', timeout=2).read()" || exit 1
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
