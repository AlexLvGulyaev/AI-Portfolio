# AI Portfolio - Frontend Dockerfile
# Builds both public static site and admin React SPA into a single nginx image.

# ============================================================
# Stage 1: Build admin frontend
# ============================================================
FROM node:20-alpine AS admin-builder

WORKDIR /app/admin

# Install dependencies
COPY admin/package*.json ./
RUN npm ci

# Copy source and build
COPY admin/ ./
RUN npm run build

# ============================================================
# Stage 2: Production nginx image
# ============================================================
FROM nginx:alpine

# Copy admin SPA build
COPY --from=admin-builder /app/admin/dist /usr/share/nginx/html/admin

# Copy public static site files
COPY src/index.html src/contacts.html src/portfolio.html src/services.html /usr/share/nginx/html/
COPY src/assets /usr/share/nginx/html/assets/
COPY src/cases /usr/share/nginx/html/cases/
COPY src/css /usr/share/nginx/html/css/
COPY src/js /usr/share/nginx/html/js/

# Copy nginx configuration
COPY src/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
