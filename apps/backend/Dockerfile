FROM rust:1.83-slim-bookworm AS rust-engine-build
WORKDIR /src
COPY engines/rust-core/Cargo.toml ./
COPY engines/rust-core/src ./src
RUN cargo test --release && cargo build --release


FROM gcc:14-bookworm AS cpp-engine-build
WORKDIR /src
COPY engines/cpp-native/include ./include
COPY engines/cpp-native/src ./src
RUN g++ -std=c++20 -O3 -fPIC -shared -Wall -Wextra -Wpedantic -Werror \
    -Iinclude src/ithute_cpp_native.cpp -o /libithute_cpp_native.so


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    ITHUTE_RUST_CORE_LIBRARY=/opt/ithute-engines/libithute_rust_core.so \
    ITHUTE_CPP_NATIVE_LIBRARY=/opt/ithute-engines/libithute_cpp_native.so

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY apps/backend/requirements.txt .
RUN set -eux; \
    for attempt in 1 2 3; do \
        pip install --no-cache-dir --timeout 120 --retries 10 -r requirements.txt && break; \
        if [ "$attempt" -eq 3 ]; then \
            echo "pip install failed after 3 attempts" >&2; \
            exit 1; \
        fi; \
        echo "pip install failed (attempt ${attempt}/3); retrying in 10 seconds..." >&2; \
        sleep 10; \
    done

RUN mkdir -p /opt/ithute-engines
COPY --from=rust-engine-build /src/target/release/libithute_rust_core.so /opt/ithute-engines/libithute_rust_core.so
COPY --from=cpp-engine-build /libithute_cpp_native.so /opt/ithute-engines/libithute_cpp_native.so
COPY apps/backend/ .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
