# Use the official Playwright Python image (includes browsers and OS dependencies)
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

# Copy requirements and install them
COPY requirements.txt .
# Add the MCP and server dependencies
RUN pip install -r requirements.txt mcp starlette uvicorn httpx

# Copy your crawler code
COPY . .

# Expose the port
EXPOSE 8000

# Start the MCP server
CMD ["python", "mcp_server.py"]