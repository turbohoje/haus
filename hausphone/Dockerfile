FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY wemo_config.json .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV IMAGE_PATH=/imgproc/output.jpg
ENV PYTHONUNBUFFERED=1

EXPOSE 3000

ENTRYPOINT ["/entrypoint.sh"]
