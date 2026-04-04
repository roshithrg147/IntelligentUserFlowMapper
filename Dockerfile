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

# Create the results directory for SQLite persistence
RUN mkdir -p results && chmod 777 results

# Expose the dynamic Cloud Run port
EXPOSE 8080

# Start the server using the PORT environment variable provided by Cloud Run
CMD uvicorn mcp_server:app --host 0.0.0.0 --port $PORT --log-level debug
