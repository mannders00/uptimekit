FROM python:3.14.3-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
ARG RELEASE_SHA=local
ENV RELEASE_SHA=$RELEASE_SHA
COPY requirements.lock ./
RUN pip install -r requirements.lock && useradd --uid 10001 --create-home app
COPY . .
RUN python manage.py collectstatic --noinput && mkdir -p /app/media && chown -R app:app /app/media
USER 10001
CMD ["python", "-m", "uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
