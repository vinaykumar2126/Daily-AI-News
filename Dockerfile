FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app (see .dockerignore for what's excluded: .venv, .env, evals/golden, etc.)
COPY . .

# Cloud Run Jobs invoke the container's entrypoint once per execution.
ENTRYPOINT ["python", "main.py"]
