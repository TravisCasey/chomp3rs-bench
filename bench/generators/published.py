"""The published image volumes: the scanned and simulated grids that the
cubical persistence papers measured, fetched from the Open SciVis Datasets
collection and turned into cubes.

The generator takes the case name, the seed, the parameters the manifest holds
and the directory to write into, and writes `<name>.csv` and `<name>.json`
there. The name under which it is called is a key of
`bench.generators.GENERATORS`.

The parameters name a dataset of `DATASETS`, a threshold and an integer
downsampling factor. A voxel is occupied when its value is at least the
threshold, so the threshold picks out the dense material of a scan and leaves
the air behind. Downsampling is a block maximum over the thresholded volume: the
volume is cut into blocks of `factor` voxels along every axis and a block is
occupied when any voxel in it is, so a factor of 1 is the volume at full
resolution and a larger factor keeps the shape while shrinking the cube count.
Every occupied block becomes one top cube, at its own coordinates in the
downsampled grid.
"""

import hashlib
import urllib.request
from pathlib import Path

import numpy

from bench.cases import write_canonical, write_sidecar

PUBLISHED_DIRECTORY = Path("cases/published")
BASE_URL = "http://klacansky.com/open-scivis-datasets"
HASH_CHUNK_BYTES = 1 << 20

DATASETS = {
    "silicium": {
        "file": "silicium/silicium_98x34x34_uint8.raw",
        "shape": (34, 34, 98),
        "voxel_type": "uint8",
        "sha512": "8ef2b9a84eb94693596b57f3f21f5ea75c1c25654011e3aed39a27f5e4259ebbbd2486ff39bb32b551bb44f3fa25123e7128cfd3fc053134f0806e23bb24a819",
    },
    "fuel": {
        "file": "fuel/fuel_64x64x64_uint8.raw",
        "shape": (64, 64, 64),
        "voxel_type": "uint8",
        "sha512": "77fdd7c657da1946bafc84e88c6b8a03ae104a79a5bdec3c7db9257480ef4bf72551a08d22fd237c8e387dd2571b575f1a1a11f5f32b1fa4d4ef385d9fe1d613",
    },
    "marschner_lobb": {
        "file": "marschner_lobb/marschner_lobb_41x41x41_uint8.raw",
        "shape": (41, 41, 41),
        "voxel_type": "uint8",
        "sha512": "608d19d1e53c8ac3fd4d3d5b230b43c129452bb8f9edccc33d7161c1644f871e0a92572c1215f7eb1a96f801e46221fc809a618c38fd1b66f63e063a3f133186",
    },
    "neghip": {
        "file": "neghip/neghip_64x64x64_uint8.raw",
        "shape": (64, 64, 64),
        "voxel_type": "uint8",
        "sha512": "d00f95d1f4cb1da2f3260a722059527ace73514cd57e1c31b6724d18468fd81002f5da704a0c3c7ccf06a329a975dede38cfacf13387dea9ffd8d7542cae62d0",
    },
    "hydrogen_atom": {
        "file": "hydrogen_atom/hydrogen_atom_128x128x128_uint8.raw",
        "shape": (128, 128, 128),
        "voxel_type": "uint8",
        "sha512": "bc80b55ffc983f41b3981433707b59f6c8b3f16cc9cd3ea18087cb9e734b702eb1ad0410f36f38881b2e2fa85617dc0858bb2d9fbd3188abb39af43ea84e3521",
    },
    "engine": {
        "file": "engine/engine_256x256x128_uint8.raw",
        "shape": (128, 256, 256),
        "voxel_type": "uint8",
        "sha512": "f17228483b1b5edb90146eac90ba979531629a2880d9e7a0493a98290da8af6ac2cf80f2c567a3d08695dc7dd854916c861dad8856b2d5721501954e913de13f",
    },
    "tooth": {
        "file": "tooth/tooth_103x94x161_uint8.raw",
        "shape": (161, 94, 103),
        "voxel_type": "uint8",
        "sha512": "5ee3d77ae951e129d29062a4fd4d8730fd8670bdaf4d01ddf907848072180cbfea8ab897880147d2a79dc7f1d1806a34b32853074eca88f6758e01382469f9f6",
    },
    "aneurism": {
        "file": "aneurism/aneurism_256x256x256_uint8.raw",
        "shape": (256, 256, 256),
        "voxel_type": "uint8",
        "sha512": "31f1232cbf75b0182f172375e46cc57fe013c0edaae292f2358e2477052ca974faae92efd803a2d229172b851b5ddaa461129872b89bd6ce45d43bfe595eed43",
    },
    "bonsai": {
        "file": "bonsai/bonsai_256x256x256_uint8.raw",
        "shape": (256, 256, 256),
        "voxel_type": "uint8",
        "sha512": "b34156a0ffc80ffaf84d069f3d05a40fdd999a35f05492829a2b0c13403a3147e73712b1d10c2cc34da66a59540a1632dae6adc96f3ebf3efa5d4d6c10598997",
    },
    "foot": {
        "file": "foot/foot_256x256x256_uint8.raw",
        "shape": (256, 256, 256),
        "voxel_type": "uint8",
        "sha512": "56a73bd1f694a09809688f5b0bbf0dfff0ef3e853a34c60c4d51bef02dd96fbfe5191f47c7762bdf7caab6f9a22f1d0e830652779f87c70cc519f345221edd0e",
    },
    "vertebra": {
        "file": "vertebra/vertebra_512x512x512_uint16.raw",
        "shape": (512, 512, 512),
        "voxel_type": "uint16",
        "sha512": "afe80be8eebbc99501ce4fc0c2ef3c8bee3d641b3a5fe70603c89675237795d8032933e2b07872fecac198ef43148c3d7531e98deddfb729ba6e64cdcf625f04",
    },
}


def published(name, seed, parameters, output_directory):
    dataset_name = parameters["dataset"]
    threshold = parameters["threshold"]
    downsample = parameters["downsample"]
    dataset = DATASETS[dataset_name]
    path = fetch(dataset)
    volume = read_volume(path, dataset)
    occupied = block_maximum(volume >= threshold, downsample)
    case_path = output_directory / f"{name}.csv"
    write_canonical(case_path, numpy.argwhere(occupied))
    write_sidecar(
        case_path,
        columns="plain",
        family="published",
        source={
            "kind": "generated",
            "generator": "published",
            "seed": seed,
            "parameters": parameters,
            "url": f"{BASE_URL}/{dataset['file']}",
            "sha512": dataset["sha512"],
            "threshold": threshold,
            "downsample": downsample,
        },
    )


def fetch(dataset):
    """The downloaded volume, fetched only when the file on disk is not already
    the one the collection publishes."""
    path = PUBLISHED_DIRECTORY / Path(dataset["file"]).name
    if path.exists() and file_hash(path) == dataset["sha512"]:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(f"{BASE_URL}/{dataset['file']}", path)
    assert file_hash(path) == dataset["sha512"]
    return path


def file_hash(path):
    digest = hashlib.sha512()
    with open(path, "rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def read_volume(path, dataset):
    voxel_type = numpy.dtype(dataset["voxel_type"]).newbyteorder("<")
    return numpy.fromfile(path, dtype=voxel_type).reshape(dataset["shape"])


def block_maximum(occupied, factor):
    """The volume cut into blocks of `factor` voxels along every axis, a block
    occupied where any voxel in it is. Voxels past the last whole block along an
    axis are dropped."""
    if factor == 1:
        return occupied
    sides = [size // factor for size in occupied.shape]
    trimmed = occupied[tuple(slice(0, side * factor) for side in sides)]
    blocked = trimmed.reshape([length for side in sides for length in (side, factor)])
    return blocked.any(axis=tuple(range(1, 2 * len(sides), 2)))
