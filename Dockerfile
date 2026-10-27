FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.lock ./
RUN pip install --no-deps -r requirements.lock

COPY app ./app
COPY frontend ./frontend
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

RUN useradd --system --create-home --uid 10001 fireops \
    && chown -R fireops:fireops /app

USER fireops

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
