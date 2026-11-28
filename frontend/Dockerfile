# Frontend Next.js - SmartCampus AI
FROM node:20-alpine

WORKDIR /app

# URL de l'API appelée par le navigateur (via localhost:8000 mappe par docker-compose)
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1

# Dependances
COPY package.json package-lock.json ./
RUN npm ci --include=dev

# Code et build de production
COPY . .
RUN npm run build
ENV NODE_ENV=production

EXPOSE 3000

CMD ["npm", "start"]
