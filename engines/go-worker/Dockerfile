FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/ithute-go-worker ./cmd/worker

FROM alpine:3.21
RUN addgroup -S ithute && adduser -S -G ithute ithute
COPY --from=build /out/ithute-go-worker /usr/local/bin/ithute-go-worker
USER ithute
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/ithute-go-worker"]
