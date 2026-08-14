# GoreeCloud Notes API development image.
# Production image publication requires separate validation and approval.
FROM python:3.13.14-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

RUN python -m pip install .

RUN useradd \
    --create-home \
    --uid 10001 \
    --shell /usr/sbin/nologin \
    goreecloud

RUN mkdir -p /var/lib/goreecloud-notes/attachments \
    && chown -R goreecloud:goreecloud /app /var/lib/goreecloud-notes
USER goreecloud

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
