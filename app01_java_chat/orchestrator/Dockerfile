FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# docker-compose.yml does not set ORCHESTRATOR_PORT and maps host 8000:8000,
# so the container must listen on 8000 regardless of whether the env var is
# present — default it in the shell form of CMD rather than relying on it
# being injected.
ENV ORCHESTRATOR_PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${ORCHESTRATOR_PORT:-8000}"]
