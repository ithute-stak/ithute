FROM eclipse-temurin:21-jdk-alpine AS build
WORKDIR /src
COPY src ./src
RUN mkdir -p /out/classes && \
    javac --release 21 --add-modules jdk.httpserver -d /out/classes $(find src -name '*.java') && \
    jar --create --file /out/ithute-java-worker.jar --main-class com.ithute.engine.Main -C /out/classes .

FROM eclipse-temurin:21-jre-alpine
RUN apk add --no-cache wget && addgroup -S ithute && adduser -S -G ithute ithute
COPY --from=build /out/ithute-java-worker.jar /opt/ithute/ithute-java-worker.jar
USER ithute
EXPOSE 8080
ENTRYPOINT ["java","--add-modules","jdk.httpserver","-XX:MaxRAMPercentage=70","-jar","/opt/ithute/ithute-java-worker.jar"]
