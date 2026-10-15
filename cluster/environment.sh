# Modules and paths shared by the build and the runs on the cluster.
# Sourced by build.sh and run.sh, never run on its own.

module load LLVM/15.0.5-GCCcore-12.2.0
module load OpenMPI/4.1.4-GCC-12.2.0

export LIBCLANG_PATH=/usr/lib64/clang-private
export LD_LIBRARY_PATH=/usr/lib64/clang-private:${LD_LIBRARY_PATH:-}
export RUSTFLAGS="-C target-cpu=x86-64-v3"
