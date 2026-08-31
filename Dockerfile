FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py prompt_template.md ./

# Cloud Run Jobs invoke the container's entrypoint once per execution.
ENTRYPOINT ["python", "main.py"]
