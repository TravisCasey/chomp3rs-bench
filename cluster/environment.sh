# Modules and paths shared by the build and the runs on the cluster.
# Sourced by build.sh and run.sh, never run on its own.

module load OpenMPI/4.1.4-GCC-12.2.0

export LIBCLANG_PATH=/usr/lib64
export BINDGEN_EXTRA_CLANG_ARGS="-I$(gcc -print-file-name=include)"
export RUSTFLAGS="-C target-cpu=x86-64-v3"
