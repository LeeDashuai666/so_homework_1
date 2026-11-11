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
COPY patches/cmov-branchify.patch /tmp/cmov-branchify.patch
RUN git -C /llvm apply --check /tmp/cmov-branchify.patch && \
    git -C /llvm apply /tmp/cmov-branchify.patch && \
    cmake --build /build --target bolt --parallel ${BUILD_JOBS} && \
    mkdir -p /out/bin /out/lib && \
    cp /build/bin/llvm-bolt /out/bin/ && \
    cp /build/lib/libbolt_rt_*.a /out/lib/ && \
    git -C /llvm rev-parse HEAD > /out/LLVM_COMMIT && \
    sha256sum /tmp/cmov-branchify.patch > /out/PATCH_SHA256

FROM ubuntu@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852 AS runtime
ARG APT_DOWNLOAD_MODE=auto
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1
COPY scripts/install_deps.sh /tmp/install_deps.sh
RUN bash /tmp/install_deps.sh python3 clang-18 g++ binutils zlib1g libzstd1
WORKDIR /opt/homework
COPY --from=toolchain /out/ app/
COPY app/ app/
COPY runtime/ runtime/
COPY tests/ tests/
COPY scripts/ scripts/
COPY BASELINE.json BASELINE.json
COPY licenses/ licenses/
RUN python3 app/build_workload.py --compiler clang++-18 --output app/workloads/search && \
    python3 scripts/build_runtime.py --compiler clang++-18 --output runtime-build && \
    g++ -std=c++17 -O2 -g -fsanitize=address,undefined -I runtime \
      tests/test_runtime.cpp runtime/runtime.cpp runtime/plain.cpp runtime/dispatch.cpp runtime/admission.cpp \
      -o /opt/homework/controller-tests
ENTRYPOINT ["python3", "/opt/homework/scripts/entrypoint.py"]
CMD ["smoke", "--output", "/results/run"]
