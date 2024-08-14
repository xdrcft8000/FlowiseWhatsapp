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

# Copy Flowise source code
COPY ./ .

# Install Flowise dependencies and build
RUN pnpm install
RUN pnpm build

# Set the working directory for FastAPI
WORKDIR /usr/src/fastapi

# Copy FastAPI source code
COPY ./fastapi .

# Install FastAPI dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the ports for Flowise and FastAPI
EXPOSE 3000 8000

# Start both Flowise and FastAPI using a process manager like PM2
RUN npm install -g pm2

# Create a PM2 ecosystem file
RUN echo "module.exports = { \
  apps: [ \
    { \
      name: 'flowise', \
      script: 'pnpm', \
      args: 'start', \
      cwd: '/usr/src/flowise', \
      env: { \
        NODE_ENV: 'production', \
        PORT: 3000 \
      } \
    }, \
    { \
      name: 'fastapi', \
      script: 'uvicorn', \
      args: 'main:app --host 0.0.0.0 --port 8000', \
      cwd: '/usr/src/fastapi', \
      env: { \
        PYTHON_ENV: 'production' \
      } \
    } \
  ] \
};" > /usr/src/ecosystem.config.js

# Set the default command to run both apps
CMD ["pm2-runtime", "start", "/usr/src/ecosystem.config.js"]
