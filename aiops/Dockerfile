FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY aiops.py .
COPY config.py .

CMD ["python", "aiops.py"]