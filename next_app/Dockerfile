# Use Node.js as the base image
FROM node:18-alpine AS base

# Set working directory
WORKDIR /app

FROM base AS dependencies
WORKDIR /app

# Copy both package.json and package-lock.json 
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci --no-fund --no-audit --prefer-offline

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

# API URL will be set via build args
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# Production image, copy only the necessary files
FROM node:18-alpine AS runner
WORKDIR /app

# Set environment variables
ARG NODE_ENV=production
ENV NODE_ENV=$NODE_ENV

ARG ENVIRONMENT=test
ENV ENVIRONMENT=$ENVIRONMENT

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Copy built files
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/package-lock.json ./package-lock.json
COPY --from=builder /app/next.config.js ./next.config.js

# Install only production dependencies
RUN npm ci --only=production --prefer-offline

# Expose the port your app runs on
EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Start the Next.js app
CMD ["npm", "start"]