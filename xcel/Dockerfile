FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY exporter.py .

RUN mkdir -p /certs
COPY cert.pem /certs/cert.pem
COPY key.pem /certs/key.pem
RUN chmod 600 /certs/key.pem

ENV METER_IP=10.22.14.23 \
    METER_PORT=8081 \
    PORT=9101 \
    CERT_FILE=/certs/cert.pem \
    KEY_FILE=/certs/key.pem

EXPOSE 9101

CMD ["python", "-u", "exporter.py"]
