# --- Build stage ---
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build

# Cache dependency resolution separately from source changes.
COPY pom.xml .
RUN mvn -B -q dependency:go-offline || true

COPY src ./src
RUN mvn -B package -DskipTests

# --- Run stage ---
FROM eclipse-temurin:21-jre-jammy AS run
WORKDIR /app

COPY --from=build /build/target/integration-bridge.jar ./integration-bridge.jar

ENV SERVER_PORT=8080
EXPOSE 8080

ENTRYPOINT ["sh", "-c", "java -jar integration-bridge.jar --server.port=${SERVER_PORT:-8080}"]
