FROM python:3.12-alpine

RUN addgroup -g 10001 ithute && adduser -D -u 10001 -G ithute -h /home/ithute ithute
WORKDIR /opt/ithute-upload
COPY service.py zip_safety.py ./
RUN python -m py_compile service.py zip_safety.py

USER 10001:10001
EXPOSE 8096
ENTRYPOINT ["python", "/opt/ithute-upload/service.py"]
