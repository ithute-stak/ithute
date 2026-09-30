FROM docker:27-cli

RUN apk add --no-cache python3 git openssh-client \
    && addgroup -g 10001 ithute \
    && adduser -D -u 10001 -G ithute -h /home/ithute ithute
WORKDIR /opt/ithute-builder
COPY builder.py verified_zip.py ./
RUN python3 -m py_compile builder.py verified_zip.py

USER 10001:10001
ENTRYPOINT ["python3", "/opt/ithute-builder/builder.py"]
