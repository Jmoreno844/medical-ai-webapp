FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system \
    "fastapi>=0.115.0,<0.116" \
    "uvicorn[standard]>=0.34.0,<0.35" \
    "langgraph>=1.0.0,<2" \
    "langgraph-checkpoint-postgres>=2.0.0,<3" \
    "langchain-core>=0.3.0,<0.4" \
    "psycopg[binary]>=3.2.0,<4" \
    "python-dotenv>=1.0.1,<2" \
    "python-json-logger>=3.3.0,<4" \
    "pydantic-settings>=2.8.0,<3" \
    "pyjwt>=2.10.1,<3" \
    "httpx>=0.28.0,<0.29" \
    "google-cloud-aiplatform>=1.71.0,<2"

COPY app ./app

EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
