ARG BUILD_FROM=python:3.12-slim-bookworm
FROM ${BUILD_FROM}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Modelle beim Bauen laden, damit die App später ohne Internet startet
RUN python -c "from rapidocr import RapidOCR; RapidOCR()"

COPY app/ /app/

CMD ["python", "/app/server.py"]
