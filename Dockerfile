FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# System deps kept minimal. Playwright browsers are installed only when the
# checkout-assistant image is built with INSTALL_BROWSERS=1.
ARG INSTALL_BROWSERS=0

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_BROWSERS" = "1" ]; then playwright install --with-deps chromium; fi

COPY . .

EXPOSE 8000
# Default: run the dashboard. Override the command to run `watch` etc.
CMD ["python", "-m", "fyodor", "web", "--host", "0.0.0.0", "--port", "8000"]
