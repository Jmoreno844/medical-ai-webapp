FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Update pip and install dependencies with verbose output for debugging
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt -v && \
    pip list  # List installed packages for verification

# Create directory for service account credentials
RUN mkdir -p /app/credentials

# Copy the rest of the application code
COPY . .

# Environment variable for service account (will be overridden at runtime)
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account-key.json

# Command to run the cloud function
# Add this line to expose the port
EXPOSE 8082

# Update the command to bind to all interfaces
CMD ["functions-framework", "--target=gemini_handler", "--port=8082", "--host=0.0.0.0"]