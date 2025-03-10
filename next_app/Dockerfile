# Use Node.js as the base image
FROM node:18-alpine AS base

# Set working directory
WORKDIR /app

# Install Google Cloud SDK in production builds
FROM base AS dependencies
WORKDIR /app

# Copy package.json (without requiring yarn.lock)
COPY package.json ./

# Install dependencies
RUN npm install

# Copy the rest of your app's source code
FROM dependencies AS builder
WORKDIR /app
COPY . .

# Build the Next.js app
# The NODE_ENV will be set via Docker build args from GitHub Actions
ARG NODE_ENV=development
ENV NODE_ENV=$NODE_ENV

# The ENVIRONMENT will differentiate between test and production
ARG ENVIRONMENT=test
ENV ENVIRONMENT=$ENVIRONMENT

RUN npm run build

# Production image, copy only the necessary files
FROM node:18-alpine AS runner
WORKDIR /app

# The NODE_ENV will be set via Docker build args from GitHub Actions
ARG NODE_ENV=production
ENV NODE_ENV=$NODE_ENV

# Set the environment (test or production)
ARG ENVIRONMENT=test
ENV ENVIRONMENT=$ENVIRONMENT

# The GCP_PROJECT_ID will be set via Docker build args from GitHub Actions
ARG GCP_PROJECT_ID
ENV GCP_PROJECT_ID=$GCP_PROJECT_ID

# Install Google Cloud SDK for cloud environments
RUN apk add --no-cache python3 py3-pip curl bash && \
    curl -sSL https://sdk.cloud.google.com | bash && \
    ln -s /root/google-cloud-sdk/bin/gcloud /usr/local/bin/gcloud && \
    pip3 install google-cloud-secret-manager

# Copy built files
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/src/lib ./src/lib
COPY --from=builder /app/server.js ./server.js

# Install only production dependencies
RUN npm ci --only=production

# Expose the port your app runs on
EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Start the Next.js app
CMD ["npm", "start"]