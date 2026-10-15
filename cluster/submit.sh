#!/bin/bash
# Submit the scaling study to Slurm, from the repository root.
#
#     sbatch cluster/submit.sh [shared|distributed|all]
#
# The shared phase needs one node and the distributed phase eight, so the two
# can also go as separate jobs: sbatch --nodes=1 cluster/submit.sh shared.
#SBATCH --job-name=chomp3rs-scaling
#SBATCH --partition=normal
#SBATCH --constraint=6338
#SBATCH --nodes=8
#SBATCH --exclusive
#SBATCH --mem=120G
#SBATCH --time=04:00:00
#SBATCH --output=%x-%j.out

exec "$SLURM_SUBMIT_DIR/cluster/run.sh" "${1:-all}"
