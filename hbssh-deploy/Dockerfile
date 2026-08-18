FROM docker.1ms.run/library/rust:1.88-alpine3.21 AS builder
RUN apk add --no-cache musl-dev build-base linux-headers
WORKDIR /src
COPY Cargo.toml ./
COPY src ./src
RUN cargo build --release --locked

FROM docker.1ms.run/library/alpine:3.21
RUN apk add --no-cache ca-certificates
COPY --from=builder /src/target/release/hbssh /usr/bin/hbssh
EXPOSE 22
ENTRYPOINT ["/usr/bin/hbssh"]
