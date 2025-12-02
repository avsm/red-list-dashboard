#!/usr/bin/env python3
"""
Species Candidate Location Finder

Train a classifier on known occurrences vs background locations,
then predict across the region to find candidate locations.

Approach mirrors brambles-tessera notebook.

Usage:
    uv run python run.py "Quercus robur" --region cambridge
"""

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import rasterio
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
CACHE_DIR = PROJECT_ROOT / "cache"

REGIONS = {
    "cambridge": {"bbox": (0.03, 52.13, 0.22, 52.29)},
}


def get_species_key(species_name: str) -> int:
    import requests
    resp = requests.get("https://api.gbif.org/v1/species/match", params={"name": species_name})
    resp.raise_for_status()
    key = resp.json().get("usageKey")
    if not key:
        raise ValueError(f"Species not found: {species_name}")
    return key


def fetch_occurrences(taxon_key: int, bbox: tuple) -> list:
    import requests
    min_lon, min_lat, max_lon, max_lat = bbox
    results = []
    offset = 0
    while True:
        resp = requests.get("https://api.gbif.org/v1/occurrence/search", params={
            "taxonKey": taxon_key, "hasCoordinate": "true", "hasGeospatialIssue": "false",
            "decimalLatitude": f"{min_lat},{max_lat}", "decimalLongitude": f"{min_lon},{max_lon}",
            "limit": 300, "offset": offset
        })
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("results", [])
        if not batch:
            break
        results.extend(batch)
        if len(results) >= data.get("count", 0):
            break
        offset += 300
    return [(r["decimalLongitude"], r["decimalLatitude"]) for r in results
            if r.get("decimalLatitude") and r.get("decimalLongitude")]


def generate_negatives(positives: list, bbox: tuple, n_samples: int, seed: int = 42) -> list:
    """Generate random background points avoiding positive locations."""
    np.random.seed(seed)
    min_lon, min_lat, max_lon, max_lat = bbox
    pos_arr = np.array(positives)
    negatives = []
    min_dist = 0.005  # ~500m

    for _ in range(n_samples * 100):
        if len(negatives) >= n_samples:
            break
        lon = np.random.uniform(min_lon, max_lon)
        lat = np.random.uniform(min_lat, max_lat)
        dists = np.sqrt((pos_arr[:, 0] - lon)**2 + (pos_arr[:, 1] - lat)**2)
        if dists.min() > min_dist:
            negatives.append((lon, lat))
    return negatives


def load_mosaic(cache_dir: Path, bbox: tuple, year: int = 2024):
    """Load and stitch tiles into a single mosaic (like brambles approach)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    tile_dir = cache_dir / str(year)

    # Find tiles covering bbox
    step = 0.1
    tile_lons = np.arange(np.floor((min_lon + 0.05) / step) * step - 0.05, max_lon + step, step)
    tile_lats = np.arange(np.floor((min_lat + 0.05) / step) * step - 0.05, max_lat + step, step)

    tiles = {}
    for tlon in tile_lons:
        for tlat in tile_lats:
            tlon, tlat = round(tlon, 2), round(tlat, 2)
            name = f"grid_{tlon:.2f}_{tlat:.2f}"
            npy = tile_dir / name / f"{name}.npy"
            scales = tile_dir / name / f"{name}_scales.npy"
            if npy.exists() and scales.exists():
                data = np.load(npy).astype(np.float32) * np.load(scales)[:, :, np.newaxis]
                tiles[(tlon, tlat)] = data

    if not tiles:
        raise ValueError(f"No tiles found in {tile_dir}")

    # Get tile dimensions (assume all same size)
    sample_tile = next(iter(tiles.values()))
    tile_h, tile_w, n_channels = sample_tile.shape

    # Sort tile coordinates
    unique_lons = sorted(set(t[0] for t in tiles.keys()))
    unique_lats = sorted(set(t[1] for t in tiles.keys()), reverse=True)  # Top to bottom

    # Stitch mosaic
    mosaic_h = len(unique_lats) * tile_h
    mosaic_w = len(unique_lons) * tile_w
    mosaic = np.zeros((mosaic_h, mosaic_w, n_channels), dtype=np.float32)

    for i, tlat in enumerate(unique_lats):
        for j, tlon in enumerate(unique_lons):
            if (tlon, tlat) in tiles:
                tile = tiles[(tlon, tlat)]
                h, w = tile.shape[:2]
                mosaic[i*tile_h:i*tile_h+h, j*tile_w:j*tile_w+w, :] = tile

    # Create transform
    mosaic_min_lon = min(unique_lons)
    mosaic_max_lat = max(unique_lats) + step
    transform = rasterio.transform.from_bounds(
        mosaic_min_lon, mosaic_max_lat - step * len(unique_lats),
        mosaic_min_lon + step * len(unique_lons), mosaic_max_lat,
        mosaic_w, mosaic_h
    )

    logger.info(f"  Loaded mosaic: {mosaic_h} x {mosaic_w} x {n_channels}")
    return mosaic, transform


def sample_embeddings(mosaic: np.ndarray, transform, coords: list) -> tuple:
    """Sample embeddings at given coordinates."""
    embeddings, valid_coords = [], []
    h, w = mosaic.shape[:2]

    for lon, lat in coords:
        row, col = rasterio.transform.rowcol(transform, lon, lat)
        if 0 <= row < h and 0 <= col < w:
            embeddings.append(mosaic[row, col, :])
            valid_coords.append((lon, lat))

    return np.array(embeddings), valid_coords


def run(species_name: str, bbox: tuple, output_dir: Path):
    logger.info("=" * 60)
    logger.info(f"Finding candidates for: {species_name}")
    logger.info("=" * 60)

    # 1. Fetch occurrences
    logger.info("\n[1/4] Fetching GBIF occurrences...")
    taxon_key = get_species_key(species_name)
    positives = fetch_occurrences(taxon_key, bbox)
    logger.info(f"  Found {len(positives)} occurrences")

    if len(positives) < 5:
        logger.error("Need at least 5 occurrences")
        return

    # 2. Load mosaic
    logger.info("\n[2/4] Loading embedding mosaic...")
    mosaic, transform = load_mosaic(CACHE_DIR, bbox)
    mosaic_h, mosaic_w, n_channels = mosaic.shape

    # 3. Prepare training data
    logger.info("\n[3/4] Preparing training data...")

    # Sample positive embeddings
    X_pos, valid_positives = sample_embeddings(mosaic, transform, positives)
    logger.info(f"  Positive samples: {len(X_pos)}")

    # Generate and sample negative embeddings
    negatives = generate_negatives(valid_positives, bbox, n_samples=len(valid_positives) * 5)
    X_neg, valid_negatives = sample_embeddings(mosaic, transform, negatives)
    logger.info(f"  Negative samples: {len(X_neg)}")

    # Combine
    X_train = np.vstack([X_pos, X_neg])
    y_train = np.array([1] * len(X_pos) + [0] * len(X_neg))
    logger.info(f"  Total training: {len(X_train)}")

    # Train classifier (like brambles: KNN with scaler)
    logger.info("  Training KNN classifier...")
    k = min(10, len(X_train) // 2)
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("knn", KNeighborsClassifier(n_neighbors=k, weights='distance'))
    ])
    model.fit(X_train, y_train)

    # 4. Predict on full mosaic
    logger.info("\n[4/4] Predicting on full mosaic...")
    all_pixels = mosaic.reshape(-1, n_channels)
    n_pixels = all_pixels.shape[0]

    # Batched prediction (like brambles)
    batch_size = 15000
    probabilities = np.zeros(n_pixels, dtype=np.float32)

    for i in tqdm(range(0, n_pixels, batch_size), desc="Classifying"):
        end = min(i + batch_size, n_pixels)
        probs = model.predict_proba(all_pixels[i:end])
        probabilities[i:end] = probs[:, 1]  # Probability of positive class

    prob_map = probabilities.reshape(mosaic_h, mosaic_w)

    # Stats
    logger.info(f"  Probability range: {probabilities.min():.3f} - {probabilities.max():.3f}")
    high_prob = (probabilities > 0.7).sum()
    logger.info(f"  High probability pixels (>0.7): {high_prob:,} ({100*high_prob/n_pixels:.1f}%)")

    # Save outputs
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save probability raster as GeoTIFF
    tiff_path = output_dir / "probability.tif"
    with rasterio.open(
        tiff_path, 'w', driver='GTiff',
        height=mosaic_h, width=mosaic_w, count=1,
        dtype=np.float32, crs='EPSG:4326', transform=transform
    ) as dst:
        dst.write(prob_map, 1)
    logger.info(f"  Saved: {tiff_path}")

    # Save high-probability candidates as GeoJSON
    threshold = 0.6
    candidates = []
    rows, cols = np.where(prob_map >= threshold)

    # Subsample if too many
    if len(rows) > 5000:
        idx = np.random.choice(len(rows), 5000, replace=False)
        rows, cols = rows[idx], cols[idx]

    for row, col in zip(rows, cols):
        lon, lat = rasterio.transform.xy(transform, row, col)
        candidates.append({
            "type": "Feature",
            "properties": {"probability": float(prob_map[row, col])},
            "geometry": {"type": "Point", "coordinates": [lon, lat]}
        })

    candidates.sort(key=lambda f: f["properties"]["probability"])

    geojson = {
        "type": "FeatureCollection",
        "features": candidates,
        "metadata": {
            "species": species_name,
            "taxon_key": taxon_key,
            "n_occurrences": len(valid_positives),
            "n_candidates": len(candidates),
            "threshold": threshold
        }
    }

    geojson_path = output_dir / "candidates.geojson"
    with open(geojson_path, "w") as f:
        json.dump(geojson, f)
    logger.info(f"  Saved: {geojson_path}")

    # Save occurrences
    occ_geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [lon, lat]}}
            for lon, lat in valid_positives
        ]
    }
    with open(output_dir / "occurrences.geojson", "w") as f:
        json.dump(occ_geojson, f, indent=2)

    logger.info("\n" + "=" * 60)
    logger.info("COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Output: {output_dir}/")


def main():
    parser = argparse.ArgumentParser(description="Find candidate locations for a species")
    parser.add_argument("species", help="Scientific name")
    parser.add_argument("--region", choices=REGIONS.keys())
    parser.add_argument("--bbox", help="min_lon,min_lat,max_lon,max_lat")
    parser.add_argument("-o", "--output")

    args = parser.parse_args()

    if args.region:
        bbox = REGIONS[args.region]["bbox"]
    elif args.bbox:
        bbox = tuple(map(float, args.bbox.split(",")))
    else:
        parser.error("Specify --region or --bbox")

    slug = args.species.lower().replace(" ", "_")
    output_dir = Path(args.output) if args.output else OUTPUT_DIR / slug

    run(args.species, bbox, output_dir)


if __name__ == "__main__":
    main()
