# AI Gateway Service - Simple Working Version for MVP
FROM node:20-alpine

WORKDIR /app

# Install curl for health checks
RUN apk add --no-cache curl

# Copy the simple working server
COPY simple-ai-gateway-server.cjs ./

# Install only express dependency
RUN npm install express@latest && npm cache clean --force

# Expose port
EXPOSE 5052

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5052/health || exit 1

# Start the simple AI Gateway server
CMD ["node", "simple-ai-gateway-server.cjs"]
