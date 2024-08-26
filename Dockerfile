# Use an official Node.js runtime as a parent image
FROM node:20-alpine

# Install necessary packages
RUN apk add --update libc6-compat python3 make g++ \
    && apk add --no-cache build-base cairo-dev pango-dev \
    && apk add --no-cache chromium \
    && apk add --no-cache py3-pip

# Install PNPM globally
RUN npm install -g pnpm

# Set environment variables for Puppeteer
ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser

# Increase Node.js memory limit
ENV NODE_OPTIONS=--max-old-space-size=8192

# Set the working directory for Flowise
WORKDIR /usr/src/flowise

# Copy Flowise source code and install dependencies
COPY ./ .
RUN pnpm install && pnpm build

# Set the working directory for FastAPI
WORKDIR /usr/src/fastapi

# Copy FastAPI source code and create a virtual environment for Python dependencies
COPY ./fastapi .
RUN python3 -m venv /usr/src/fastapi/venv \
    && /usr/src/fastapi/venv/bin/pip install --no-cache-dir -r requirements.txt

# Expose the ports for Flowise and FastAPI
EXPOSE 3000 8000

# Start both Flowise and FastAPI directly
CMD ["sh", "-c", "cd /usr/src/flowise && pnpm start & /usr/src/fastapi/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000"]
