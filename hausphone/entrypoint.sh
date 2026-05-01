#!/bin/sh
set -e
CERT_DIR=/certs
mkdir -p "$CERT_DIR"

if [ ! -f "$CERT_DIR/cert.pem" ]; then
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "$CERT_DIR/key.pem" \
        -out "$CERT_DIR/cert.pem" \
        -subj "/CN=10.22.14.2" \
        -addext "subjectAltName=IP:10.22.14.2,IP:127.0.0.1"
    echo "Generated self-signed certificate at $CERT_DIR/cert.pem"
fi

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 3000 \
    --ssl-keyfile "$CERT_DIR/key.pem" \
    --ssl-certfile "$CERT_DIR/cert.pem"
