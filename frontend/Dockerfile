# ============================================================
# Frontend image — Vite build served by nginx.
# ============================================================
# Two targets:
#   development — the Vite dev server, with hot reload against a mounted source
#   production  — a static build served by nginx, ~25 MB total

FROM node:20-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ------------------------------------------------------------
FROM deps AS development

COPY . .
EXPOSE 3000
# --host so the server binds 0.0.0.0 and is reachable from outside the container.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]

# ------------------------------------------------------------
FROM deps AS build

COPY . .

# Vite inlines VITE_* variables at BUILD time, not at runtime — the bundle is
# static files with the values already baked in. So these must be build args,
# and changing one means rebuilding the image, not restarting the container.
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_GOOGLE_CLIENT_ID=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID

RUN npm run build

# ------------------------------------------------------------
FROM nginx:1.27-alpine AS production

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
