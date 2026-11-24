FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FIN_EVIDENCE_DATA=/app/data

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY data ./data

ENTRYPOINT ["fin-evidence", "--data", "/app/data", "serve"]
