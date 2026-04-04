# Use the official Playwright Python image
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

# Set environment variables for non-interactive installs and production
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080

WORKDIR /app

# Copy only requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies and Chromium
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

# Copy the rest of the application code
COPY . .

# Create the results directory for SQLite persistence and drop root
RUN useradd -m crawler_user && \
    mkdir -p results && chown -R crawler_user:crawler_user /app && \
    chmod 755 results

USER crawler_user

# Start the server using the python entrypoint to properly bind the PORT
CMD ["python", "mcp_server.py"]
