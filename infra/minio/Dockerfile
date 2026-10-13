# Build archived upstream community sources; public binary images are unavailable.
FROM golang:1.24.13-alpine AS server-build
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/minio/minio.git \
    && git fetch --depth 1 origin 7aac2a2c5b7c882e68c1ce017d8256be2feea27f \
    && git checkout --detach FETCH_HEAD
RUN GOMAXPROCS=1 GOMEMLIMIT=1GiB GOGC=20 CGO_ENABLED=0 go build -p 1 -trimpath -o /out/minio .

FROM golang:1.24.13-alpine AS client-build
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/minio/mc.git \
    && git fetch --depth 1 origin 77f82e18b5401a65958f1619df6ebb994634bd88 \
    && git checkout --detach FETCH_HEAD
RUN GOMAXPROCS=1 GOMEMLIMIT=1GiB GOGC=20 CGO_ENABLED=0 go build -p 1 -trimpath -o /out/mc .

FROM alpine:3.23 AS server
RUN apk add --no-cache ca-certificates curl
COPY --from=server-build /out/minio /usr/local/bin/minio
COPY --from=server-build /src/LICENSE /usr/share/licenses/minio/LICENSE
EXPOSE 9000 9001
ENTRYPOINT ["minio"]

FROM alpine:3.23 AS client
RUN apk add --no-cache ca-certificates
COPY --from=client-build /out/mc /usr/local/bin/mc
COPY --from=client-build /src/LICENSE /usr/share/licenses/mc/LICENSE
ENTRYPOINT ["mc"]
