# KUSANYA — application image.
# Single image used for web, celery worker, and celery beat (see
# docker-compose.yml); the CMD differs per service, the image doesn't.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
RUN pip install --upgrade pip && pip install -r requirements/development.txt

COPY . .

RUN useradd --create-home --uid 1000 kusanya \
    && chown -R kusanya:kusanya /app
USER kusanya

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
