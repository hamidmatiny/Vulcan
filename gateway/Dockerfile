# CPU-only gateway image (ADR-002).
FROM golang:1.25-alpine AS build
WORKDIR /src
COPY gateway/go.mod gateway/go.sum* ./
RUN go mod download
COPY gateway/ ./
RUN CGO_ENABLED=0 go build -o /gateway ./cmd/gateway

FROM alpine:3.20
RUN apk add --no-cache ca-certificates curl
WORKDIR /app
COPY --from=build /gateway /app/gateway
COPY gateway/resource-requirements.json /app/resource-requirements.json
ENV PORT=9007
ENV VULCAN_RESOURCES_PATH=/app/resource-requirements.json
EXPOSE 9007
HEALTHCHECK --interval=10s --timeout=5s --retries=12 --start-period=10s \
  CMD curl -fsS http://127.0.0.1:9007/health || exit 1
ENTRYPOINT ["/app/gateway"]
