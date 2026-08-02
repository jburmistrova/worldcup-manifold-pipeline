# eclipse-temurin already carries the Java 25 PySpark needs (JAVA_HOME
# preconfigured to /opt/java/openjdk) and its Ubuntu 26.04 base's own apt
# repo happens to package exactly Python 3.14 as `python3`. Installing
# both runtimes from one distro's package manager, rather than copying
# Python binaries in from a second, differently-based image (python:3.14-slim
# is Debian, not Ubuntu, cross-distro glibc/library assumptions are a real
# way multi-stage copies break).
FROM eclipse-temurin:25-jre

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python3 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt
ENV PATH="/venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

COPY ingest/ ingest/
COPY spark/ spark/
COPY dbt/ dbt/
COPY analysis/ analysis/
COPY run_pipeline.sh .
RUN chmod +x run_pipeline.sh

# resolved once here, at build time, baked into the image, not at
# container startup, which would mean every Job run needs network access to
# fetch dbt_utils and could fail on the same class of external-dependency
# flakiness this project already hit once with the Manifold API itself
RUN cd dbt && dbt deps

ENTRYPOINT ["./run_pipeline.sh"]
