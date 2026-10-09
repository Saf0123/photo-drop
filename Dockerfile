FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /srv
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .
RUN useradd -m appuser && chown -R appuser /srv
USER appuser
CMD exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 4 "main:create_app()"
