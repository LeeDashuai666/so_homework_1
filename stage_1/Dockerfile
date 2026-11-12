FROM ubuntu@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852 AS toolchain
ARG BUILD_JOBS=2
ARG APT_DOWNLOAD_MODE=auto
ENV DEBIAN_FRONTEND=noninteractive
COPY scripts/install_deps.sh /tmp/install_deps.sh
RUN bash /tmp/install_deps.sh \
      ca-certificates git cmake ninja-build gcc g++ lld python3 binutils \
      zlib1g-dev libzstd-dev
ARG GIT_DOWNLOAD_MODE=auto
COPY scripts/fetch_llvm.sh /tmp/fetch_llvm.sh
RUN bash /tmp/fetch_llvm.sh
RUN cmake -S /llvm/llvm -B /build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ \
      -DLLVM_USE_LINKER=lld -DLLVM_ENABLE_PROJECTS=bolt \
      -DLLVM_TARGETS_TO_BUILD=X86 -DBOLT_TARGETS_TO_BUILD=X86 \
      -DLLVM_ENABLE_ASSERTIONS=ON -DLLVM_ENABLE_LTO=OFF -DBOLT_ENABLE_RUNTIME=ON \
      -DLLVM_INCLUDE_TESTS=OFF -DBOLT_INCLUDE_TESTS=OFF \
      -DLLVM_ENABLE_ZLIB=FORCE_ON -DLLVM_ENABLE_ZSTD=FORCE_ON \
      -DLLVM_ENABLE_LIBXML2=OFF -DLLVM_ENABLE_CURL=OFF \
      -DLLVM_PARALLEL_COMPILE_JOBS=${BUILD_JOBS} -DLLVM_PARALLEL_LINK_JOBS=1 && \
    cmake --build /build --target bolt --parallel ${BUILD_JOBS} && \
    mkdir -p /out/baseline/bin /out/baseline/lib && \
    cp /build/bin/llvm-bolt /out/baseline/bin/ && \
    cp /build/lib/libbolt_rt_*.a /out/baseline/lib/
COPY patches/cmov-runtime.patch /tmp/cmov-runtime.patch
RUN git -C /llvm apply --check /tmp/cmov-runtime.patch && \
    git -C /llvm apply /tmp/cmov-runtime.patch && \
    cmake --build /build --target bolt --parallel ${BUILD_JOBS} && \
    mkdir -p /out/build/bin /out/build/lib && \
    cp /build/bin/llvm-bolt /out/build/bin/ && \
    cp /build/lib/libbolt_rt_*.a /out/build/lib/ && \
    git -C /llvm rev-parse HEAD > /out/LLVM_COMMIT && \
    sha256sum /tmp/cmov-runtime.patch > /out/PATCH_SHA256



FROM ubuntu@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852 AS runtime
ARG APT_DOWNLOAD_MODE=auto
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1
COPY scripts/install_deps.sh /tmp/install_deps.sh
RUN bash /tmp/install_deps.sh python3 clang-18 g++ binutils zlib1g libzstd1
WORKDIR /opt/homework
COPY --from=toolchain /out/ ./
COPY project/ project/
COPY runtime/ runtime/
COPY scripts/ scripts/
COPY licenses/ licenses/
COPY BASELINE.json BASELINE.json
RUN python3 project/cmov_branchify/build_workload.py --compiler clang++-18 --output project/cmov_branchify/workloads/search && \
    g++ -std=c++17 -O2 -g -fsanitize=address,undefined -DBOLT_CMOV_TEST_CLOCK \
      -I project/cmov_runtime project/cmov_runtime/test_runtime.cpp runtime/cmov.cpp runtime/cmov_observe.cpp \
      -o controller-tests
ENTRYPOINT ["python3", "/opt/homework/scripts/entrypoint.py"]
CMD ["smoke", "--output", "/results/run"]
