#!/bin/bash
# Build the chomp3rs driver with its MPI backends.
#
#     cluster/build.sh
#
# Needs rustup in the home directory; the driver's rust-toolchain.toml names
# the Rust release, which cargo installs on first use.

set -euo pipefail

repository=$(cd "$(dirname "$0")/.." && pwd)
source "$repository/cluster/environment.sh"

cargo build --release --locked --features mpi --manifest-path "$repository/driver/Cargo.toml"
