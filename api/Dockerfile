FROM python:3.12-slim

WORKDIR /app

# System dependency for graphviz
RUN apt-get update && apt-get install -y --no-install-recommends graphviz && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY api/ ./api/

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
