# Data-Deficient Plant Search

Identify candidate locations for collecting samples for a plant species using embeddings from geospatial foundation models.

## Why This Matters

GBIF has occurrence data for 354,357 plant species, but:
- **72.6%** have 100 or fewer occurrences
- **36.6%** have 10 or fewer occurrences
- **9.3%** have just 1 occurrence

This tool helps conservation biologists find where to look for rare/data-deficient plants by learning habitat signatures from known locations.

## Quick Start

```bash
# Find candidate locations for Common Oak in Cambridge area
uv run python run.py "Quercus robur" --region cambridge
```

This will:
1. Fetch known occurrences from GBIF
2. Sample Tessera embeddings at those locations
3. Train a classifier to recognize the habitat signature
4. Scan the region to find candidate locations
5. Save results to `output/quercus_robur/`

## Usage

```bash
# Using a predefined region
uv run python run.py "Quercus robur" --region cambridge
uv run python run.py "Quercus robur" --region uk

# Using a custom bounding box (min_lon,min_lat,max_lon,max_lat)
uv run python run.py "Adansonia digitata" --bbox -20,10,50,25

# Custom output directory
uv run python run.py "Quercus robur" --region cambridge -o my_output/
```

## Requirements

**Tessera embeddings cache**: The pipeline requires pre-downloaded Tessera embeddings in `cache/2024/`. These are 0.1° tiles of 128-dimensional embeddings from the Tessera geospatial foundation model.

## Output

Results are saved to `output/{species_name}/`:
- `candidates.geojson` - Predicted candidate locations with probability scores
- `occurrences.geojson` - Known GBIF occurrences used for training
- `model.joblib` - Trained classifier (can be reused)

## Web App

Visualize results and explore GBIF data:

```bash
cd app
npm install
npm run dev
```

Open http://localhost:3000 to:
- Browse plant species by occurrence count
- View occurrence maps
- Overlay AI-predicted candidate locations

## Project Structure

```
/
├── run.py          # Main CLI - the only script you need
├── app/            # Next.js visualization app
├── cache/          # Tessera embeddings (gitignored)
└── output/         # Generated results (gitignored)
```
