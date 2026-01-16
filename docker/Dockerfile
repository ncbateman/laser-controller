FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:${PATH}"

COPY src src

COPY pyproject.toml pyproject.toml

RUN uv pip install --system --break-system-packages -e .

CMD ["uvicorn", "api.asgi:factory", "--host", "0.0.0.0", "--port", "80", "--reload", "--factory"]
