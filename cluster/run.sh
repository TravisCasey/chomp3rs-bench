#!/bin/bash
# Run the chomp3rs scaling study inside a Slurm allocation of whole nodes.
#
#     cluster/run.sh shared|distributed|all
#
# The shared phase runs the sequential backend once and the Rayon backend at
# each thread count on the first node of the allocation. The distributed phase
# runs the MPI backend at one rank per core and the hybrid backend at one
# worker rank per node, on the first 1, 2, 4 and 8 nodes. Rank 0 of both only
# hands out work, so the hybrid runs place it on the first node beside that
# node's worker, which keeps every core of the node.
#
# Each run writes one JSON file under results/runs/cluster/<job id>/ holding
# the layout, the hosts, the exit status, the wall time measured around the
# launch and the driver's own record; environment.txt beside them holds the
# modules, the processor, the compilers and the repository commit.

set -euo pipefail

phase=$1
repository=$(cd "$(dirname "$0")/.." && pwd)
source "$repository/cluster/environment.sh"

case_path=$repository/cases/flows/kuramoto_sivashinsky_d16_box0.125.csv
driver=$repository/driver/target/release/chomp3rs-driver
cores_per_node=64
rayon_threads=(2 4 8 16 32 64)
node_counts=(1 2 4 8)
repetitions=2
timeout_seconds=5400
output=$repository/results/runs/cluster/$SLURM_JOB_ID

mkdir -p "$output"
mapfile -t hosts < <(scontrol show hostnames "$SLURM_JOB_NODELIST")

commit=$(git -C "$repository" rev-parse HEAD)
if ! git -C "$repository" diff --quiet HEAD; then
    commit=$commit-dirty
fi

{
    echo "job $SLURM_JOB_ID"
    echo "phase $phase"
    echo "started $(date --iso-8601=seconds)"
    echo "hosts ${hosts[*]}"
    echo "repository $commit"
    echo "rustc $(cd "$repository/driver" && rustc --version)"
    echo "mpirun $(mpirun --version | head -1)"
    echo
    module list 2>&1
    echo
    lscpu
} > "$output/environment.txt"

# measure LABEL BACKEND NODES RANKS THREADS COMMAND...
measure() {
    local label=$1 backend=$2 nodes=$3 ranks=$4 threads=$5
    shift 5
    local started finished status
    echo "$(date --iso-8601=seconds) $label"
    started=$(date +%s.%N)
    if timeout "$timeout_seconds" "$@" > "$output/$label.driver.json" 2> "$output/$label.stderr"; then
        status=finished
    else
        status="exit $?"
    fi
    finished=$(date +%s.%N)
    {
        printf '{"label": "%s", "backend": "%s", "nodes": %d, "ranks": %d, "threads": %d,' \
            "$label" "$backend" "$nodes" "$ranks" "$threads"
        printf ' "hosts": "%s", "status": "%s", "wall_seconds": %s, "driver": ' \
            "${hosts[*]:0:$nodes}" "$status" "$(awk "BEGIN { print $finished - $started }")"
        if [ -s "$output/$label.driver.json" ]; then
            cat "$output/$label.driver.json"
        else
            printf 'null'
        fi
        printf '}\n'
    } > "$output/$label.json"
    rm "$output/$label.driver.json"
}

shared() {
    measure sequential_n1_1x1_rep0 sequential 1 1 1 \
        "$driver" "$case_path" --columns plain --backend sequential
    for repetition in $(seq 0 $((repetitions - 1))); do
        for threads in "${rayon_threads[@]}"; do
            measure "rayon_n1_1x${threads}_rep$repetition" rayon 1 1 "$threads" \
                "$driver" "$case_path" --columns plain --backend rayon --threads "$threads"
        done
    done
}

distributed() {
    for repetition in $(seq 0 $((repetitions - 1))); do
        for nodes in "${node_counts[@]}"; do
            local hostfile=$output/hosts_$nodes
            printf "%s slots=$cores_per_node\n" "${hosts[@]:0:$nodes}" > "$hostfile"

            local ranks=$((nodes * cores_per_node))
            measure "mpi_n${nodes}_${ranks}x1_rep$repetition" mpi "$nodes" "$ranks" 1 \
                mpirun --hostfile "$hostfile" -np "$ranks" --map-by core --bind-to core \
                "$driver" "$case_path" --columns plain --backend mpi

            ranks=$((nodes + 1))
            measure "hybrid_n${nodes}_${ranks}x${cores_per_node}_rep$repetition" hybrid "$nodes" "$ranks" "$cores_per_node" \
                mpirun --hostfile "$hostfile" -np "$ranks" --map-by node --bind-to none \
                "$driver" "$case_path" --columns plain --backend hybrid --threads "$cores_per_node"
        done
    done
}

case $phase in
    shared) shared ;;
    distributed) distributed ;;
    all) shared; distributed ;;
esac

echo "finished $(date --iso-8601=seconds)" >> "$output/environment.txt"
