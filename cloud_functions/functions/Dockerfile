FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Update pip and install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create directory for service account credentials
RUN mkdir -p /app/credentials

# Copy the rest of the application code
COPY . .

# Environment variable for service account (will be overridden at runtime)
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account-key.json

# The target function will be specified via environment variable
ENV PORT=8082

# Use environment variable for target function
CMD functions-framework --target=${FUNCTION_TARGET} --port=${PORT} --host=0.0.0.0