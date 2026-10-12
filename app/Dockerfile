FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/

ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["uvicorn", "storefront.app:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
