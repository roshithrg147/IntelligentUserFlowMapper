# Builder Stage
FROM python:3.11-slim as builder

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Final Stage
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Install system dependencies required for Chromium cleanly
RUN apt-get update && \
    playwright install --with-deps chromium && \
    rm -rf /var/lib/apt/lists/*

# Copy the rest of the application code
COPY . .

# Create the results directory for persistence and drop root
RUN useradd -m crawler_user && \
    mkdir -p results && chown -R crawler_user:crawler_user /app

USER crawler_user

# Start the server using the python entrypoint to properly bind the PORT
CMD ["python", "mcp_server.py"]
