FROM node:20-slim AS builder

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

# Serve with nginx
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Proxy /api → backend
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
