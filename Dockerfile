FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY server.py .
COPY static/ ./static/

# Set environment variables
ENV WEB_CLIENT_PORT=8080
ENV ESP32_PORT=8081
ENV HTTP_PORT=8000

# Expose ports
EXPOSE 8000 8080 8081

# Run the server
CMD ["python", "server.py"] 
