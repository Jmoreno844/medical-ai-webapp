FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Update pip and install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Optional mount point for legacy service account JSON (see docker-compose)
RUN mkdir -p /app/credentials

# Copy the rest of the application code
COPY . .

# GOOGLE_APPLICATION_CREDENTIALS is set at runtime (docker-compose: /app/adc.json for ADC)

# The target function will be specified via environment variable
ENV PORT=8082

# Use environment variable for target function
CMD functions-framework --target=${FUNCTION_TARGET} --port=${PORT} --host=0.0.0.0