# ---- build stage ----
FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Vite bakes VITE_* vars at build time. The Clerk *publishable* key is public
# (it ships in the client bundle), so passing it as a build arg is expected.
# VITE_API_BASE_URL defaults to "" so the app calls same-origin paths that
# nginx proxies to the backend (see nginx.conf).
ARG VITE_API_BASE_URL=""
ARG VITE_CLERK_PUBLISHABLE_KEY=""
ARG VITE_TENANT_ID="default"
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY \
    VITE_TENANT_ID=$VITE_TENANT_ID

RUN npm run build

# ---- serve stage ----
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
