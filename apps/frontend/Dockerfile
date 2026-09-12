FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:20-alpine AS builder
WORKDIR /app
ENV NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
RUN addgroup -S ithute && adduser -S ithute -G ithute
COPY --from=builder --chown=ithute:ithute /app/.next/standalone ./
COPY --from=builder --chown=ithute:ithute /app/.next/static ./.next/static
USER ithute
EXPOSE 3000
HEALTHCHECK --interval=20s --timeout=4s --start-period=15s --retries=5 CMD wget -qO- http://127.0.0.1:3000/health >/dev/null || exit 1
CMD ["node", "server.js"]
