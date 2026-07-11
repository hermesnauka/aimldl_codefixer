# OpenCode Worker — this is the image for the FastAPI control-plane process
# ITSELF, not for any language runtime it launches. It does NOT need Docker
# installed inside it (no Docker-in-Docker): at runtime this container talks
# to the HOST's Docker daemon over a bind-mounted socket
# (docker-compose.yml: `- /var/run/docker.sock:/var/run/docker.sock`) to
# launch sibling containers (python:3.12-slim, node:20-slim,
# eclipse-temurin:21-jdk-alpine) for each /execute request. See README.md for
# the full security implications of that socket mount.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Matches docker-compose.yml's "8100:8100" port mapping — do not change this
# default without updating docker-compose.yml and .env.example together.
ENV WORKER_PORT=8100
EXPOSE 8100

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${WORKER_PORT:-8100}"]
