ARG BASE_DIGEST="sha256:6788062a1b42ac281f053ac876170b79a3eaed5d61383b8ed7eaca6c6965f3b1"
FROM docker.io/library/debian:13@${BASE_DIGEST}
ARG BASE_DIGEST

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      cmake \
      curl \
      git \
      libopenmpi-dev \
      openmpi-bin \
      python3 \
      python3-dev \
      python3-venv \
      time \
      unzip \
 && rm -rf /var/lib/apt/lists/*

ENV CFLAGS="-O3 -march=x86-64-v3"
ENV CXXFLAGS="-O3 -march=x86-64-v3"
ENV RUSTFLAGS="-C target-cpu=x86-64-v3"
ENV RUSTUP_HOME="/opt/rust/rustup"
ENV CARGO_HOME="/opt/rust/cargo"
ENV PATH="/opt/tools/bin:/opt/rust/cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ENV OMPI_ALLOW_RUN_AS_ROOT="1"
ENV OMPI_ALLOW_RUN_AS_ROOT_CONFIRM="1"

RUN mkdir -p /opt/tools/bin /opt/build /work \
 && python3 -m venv /opt/tools/venv \
 && printf '#!/bin/sh\nexec /opt/tools/venv/bin/python "$@"\n' > /opt/tools/bin/tools-python \
 && chmod 755 /opt/tools/bin/tools-python

ARG HOMCUBES_URL="http://www.pawelpilarczyk.com/chomp/download/chomp-full.zip"
ARG HOMCUBES_SHA256="16ff175453e17c83e5cf207a7574453dbe348a26a2129759e30fce605580dbc0"
RUN curl -fsSL -o /opt/build/chomp-full.zip "${HOMCUBES_URL}" \
 && echo "${HOMCUBES_SHA256}  /opt/build/chomp-full.zip" | sha256sum -c \
 && unzip -q /opt/build/chomp-full.zip -d /opt/build/chomp \
 && make -C /opt/build/chomp -j"$(nproc)" \
      COMPILE="g++ -Wno-unused-local-typedefs ${CXXFLAGS} -ansi -pedantic -Wall" \
 && cp /opt/build/chomp/bin/homcubes /opt/tools/bin/homcubes \
 && rm -rf /opt/build/chomp /opt/build/chomp-full.zip

ARG PYCHOMP2_REPOSITORY="https://github.com/marciogameiro/pyCHomP2"
ARG PYCHOMP2_COMMIT="b7b11af5fc387a6f55f42dd8fabb8d710e50d7c6"
RUN git clone "${PYCHOMP2_REPOSITORY}" /opt/build/pychomp2 \
 && git -C /opt/build/pychomp2 checkout "${PYCHOMP2_COMMIT}" \
 && /opt/tools/venv/bin/pip install --no-cache-dir setuptools wheel cmake pybind11 \
 && CMAKE_PREFIX_PATH="$(/opt/tools/venv/bin/python -c 'import pybind11; print(pybind11.get_cmake_dir())')" \
    /opt/tools/venv/bin/pip install --no-cache-dir --no-build-isolation /opt/build/pychomp2 \
 && rm -rf /opt/build/pychomp2

ARG PERSEUS_URL="https://people.maths.ox.ac.uk/nanda/source/perseus_4_beta.zip"
ARG PERSEUS_SHA256="7279091080b8b6ef8d8bbcf470a76398b752f102def222a9740f2e85ad8c7925"
RUN curl -fsSL -o /opt/build/perseus.zip "${PERSEUS_URL}" \
 && echo "${PERSEUS_SHA256}  /opt/build/perseus.zip" | sha256sum -c \
 && unzip -q /opt/build/perseus.zip -d /opt/build/perseus \
 && sed -i 's/bool operator() (num n1, num n2)/bool operator() (num n1, num n2) const/' /opt/build/perseus/Global/Combinatorics.h \
 && sed -i 's/bool operator () (vector<num>\* v1, vector<num>\* v2)/bool operator () (vector<num>* v1, vector<num>* v2) const/' /opt/build/perseus/Complexes/CToplex.h \
 && sed -i 's/bool operator ()(Point<PS>\* p, Point<PS>\* q)/bool operator ()(Point<PS>* p, Point<PS>* q) const/' /opt/build/perseus/Cells/Point.h \
 && cd /opt/build/perseus \
 && g++ ${CXXFLAGS} Pers.cpp -fpermissive -o /opt/tools/bin/perseus \
 && cd / \
 && rm -rf /opt/build/perseus /opt/build/perseus.zip

ARG GUDHI_VERSION="3.13.0"
RUN /opt/tools/venv/bin/pip install --no-cache-dir "gudhi==${GUDHI_VERSION}"

ARG DIPHA_REPOSITORY="https://github.com/DIPHA/dipha"
ARG DIPHA_COMMIT="0b874769fbd092c07a12cebc2459adb02117c2fd"
RUN git clone "${DIPHA_REPOSITORY}" /opt/build/dipha \
 && git -C /opt/build/dipha checkout "${DIPHA_COMMIT}" \
 && cmake -S /opt/build/dipha -B /opt/build/dipha/build \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
 && cmake --build /opt/build/dipha/build -j "$(nproc)" \
 && cp /opt/build/dipha/build/dipha /opt/tools/bin/dipha \
 && rm -rf /opt/build/dipha

ARG CUBICALRIPSER_REPOSITORY="https://github.com/shizuo-kaji/CubicalRipser"
ARG CUBICALRIPSER_COMMIT="e9632f2466674c07cda0db2f178da26007194496"
ARG NANOBIND_VERSION="3.0.1"
RUN git clone "${CUBICALRIPSER_REPOSITORY}" /opt/build/cubicalripser \
 && git -C /opt/build/cubicalripser checkout "${CUBICALRIPSER_COMMIT}" \
 && /opt/tools/venv/bin/pip install --no-cache-dir "nanobind==${NANOBIND_VERSION}" \
 && cmake -S /opt/build/cubicalripser -B /opt/build/cubicalripser/build \
      -DCMAKE_BUILD_TYPE=Release -DPython_EXECUTABLE=/opt/tools/venv/bin/python \
 && cmake --build /opt/build/cubicalripser/build -j "$(nproc)" \
 && cp /opt/build/cubicalripser/build/cubicalripser /opt/tools/bin/cubicalripser \
 && cp /opt/build/cubicalripser/build/tcubicalripser /opt/tools/bin/tcubicalripser \
 && rm -rf /opt/build/cubicalripser

ARG RUST_VERSION="1.98.1"
ARG RUSTUP_VERSION="1.29.1"
ARG RUSTUP_INIT_SHA256="dda7234360b7f578ca8b0ddcb80145646fa61a67c1720a5abc7051b35c9fcb71"
RUN curl -fsSL -o /opt/build/rustup-init \
      "https://static.rust-lang.org/rustup/archive/${RUSTUP_VERSION}/x86_64-unknown-linux-gnu/rustup-init" \
 && echo "${RUSTUP_INIT_SHA256}  /opt/build/rustup-init" | sha256sum -c \
 && chmod 755 /opt/build/rustup-init \
 && /opt/build/rustup-init -y --no-modify-path --default-toolchain "${RUST_VERSION}" --profile minimal \
 && rm -f /opt/build/rustup-init

ARG CHOMP3RS_COMMIT="2f15ddbcf96f9df2650000bf8265c28e782ce57a"
COPY driver/ /opt/driver/
RUN grep -q "rev = \"${CHOMP3RS_COMMIT}\"" /opt/driver/Cargo.toml \
 && grep -q "channel = \"${RUST_VERSION}\"" /opt/driver/rust-toolchain.toml \
 && cargo build --release --locked --manifest-path /opt/driver/Cargo.toml \
 && cp /opt/driver/target/release/chomp3rs-driver /opt/tools/bin/chomp3rs-driver \
 && rm -rf /opt/driver/target "${CARGO_HOME}/registry" "${CARGO_HOME}/git"

RUN { \
      echo "base-image docker.io/library/debian:13@${BASE_DIGEST}"; \
      echo "python $(/opt/tools/venv/bin/python -c 'import platform; print(platform.python_version())')"; \
      echo "gcc $(gcc -dumpfullversion)"; \
      echo "homcubes sha256:${HOMCUBES_SHA256}"; \
      echo "pychomp2 ${PYCHOMP2_COMMIT}"; \
      echo "perseus sha256:${PERSEUS_SHA256}"; \
      echo "gudhi ${GUDHI_VERSION}"; \
      echo "dipha ${DIPHA_COMMIT}"; \
      echo "cubicalripser ${CUBICALRIPSER_COMMIT}"; \
      echo "chomp3rs ${CHOMP3RS_COMMIT}"; \
      echo "rust ${RUST_VERSION}"; \
      echo "rustup ${RUSTUP_VERSION}"; \
    } > /opt/tools/PINS

WORKDIR /work
