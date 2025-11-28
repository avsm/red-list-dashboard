"""
Script to analyze GBIF occurrence data distribution for plant species.

This helps identify "data-deficient" species that have very few GPS samples,
which are candidates for targeted sample collection efforts.

Filters applied:
- hasCoordinate=True (only georeferenced records)
- hasGeospatialIssue=False (excluding records with known geospatial issues)
"""

import json
from pathlib import Path

import pandas as pd
from pygbif import occurrences, species


def get_species_info(scientific_name: str) -> dict | None:
    """Look up a species in GBIF backbone taxonomy."""
    result = species.name_backbone(scientificName=scientific_name, kingdom="Plantae")
    usage = result.get("usage", {})
    diagnostics = result.get("diagnostics", {})
    match_type = diagnostics.get("matchType")

    if match_type in ["EXACT", "FUZZY"]:
        classification = {
            item["rank"]: item["name"] for item in result.get("classification", [])
        }
        return {
            "scientific_name": usage.get("name", scientific_name),
            "gbif_key": int(usage.get("key")),
            "kingdom": classification.get("KINGDOM"),
            "family": classification.get("FAMILY"),
            "match_type": match_type,
        }
    return None


def get_occurrence_count(taxon_key: int) -> int:
    """Get the number of occurrence records for a species in GBIF (with geospatial filters)."""
    result = occurrences.search(
        taxonKey=taxon_key,
        hasCoordinate=True,
        hasGeospatialIssue=False,
        limit=0
    )
    return result.get("count", 0)


def test_single_species(scientific_name: str) -> None:
    """Test the GBIF API with a single species."""
    print(f"\n{'='*60}")
    print(f"Testing GBIF data retrieval for: {scientific_name}")
    print("=" * 60)

    info = get_species_info(scientific_name)
    if not info:
        print(f"Could not find species '{scientific_name}' in GBIF")
        return

    print("\nSpecies info:")
    print(f"  Scientific name: {info['scientific_name']}")
    print(f"  GBIF key: {info['gbif_key']}")
    print(f"  Kingdom: {info['kingdom']}")
    print(f"  Family: {info['family']}")
    print(f"  Match type: {info['match_type']}")

    georef_count = get_occurrence_count(info["gbif_key"])

    print("\nOccurrence counts (hasCoordinate=true, hasGeospatialIssue=false):")
    print(f"  Georeferenced records: {georef_count:,}")

    print("\nSample occurrence records (first 3):")
    sample = occurrences.search(
        taxonKey=info["gbif_key"],
        hasCoordinate=True,
        hasGeospatialIssue=False,
        limit=3
    )
    for i, record in enumerate(sample.get("results", []), 1):
        print(
            f"  {i}. {record.get('country', 'Unknown country')}: "
            f"({record.get('decimalLatitude', 'N/A')}, {record.get('decimalLongitude', 'N/A')}) "
            f"- {record.get('year', 'Unknown year')}"
        )


def fetch_all_plant_species_counts(
    output_path: Path | None = None, batch_size: int = 100000
) -> pd.DataFrame:
    """
    Fetch occurrence counts for all plant species with georeferenced records.

    Uses GBIF's facet API to efficiently retrieve counts per species without
    downloading individual occurrence records.

    Filters:
    - hasCoordinate=True (only georeferenced records)
    - hasGeospatialIssue=False (excluding records with known geospatial issues)

    Args:
        output_path: Optional path to save the results as CSV
        batch_size: Number of species to fetch per API call (max 100000)

    Returns:
        DataFrame with species_key and occurrence_count columns
    """
    print("Fetching occurrence counts for all plant species...")
    print("Filters: hasCoordinate=True, hasGeospatialIssue=False")
    print("(This may take a few minutes)")

    all_species_counts = []
    offset = 0

    while True:
        result = occurrences.search(
            kingdomKey=6,  # Plantae
            hasCoordinate=True,
            hasGeospatialIssue=False,
            limit=0,
            facet="speciesKey",
            speciesKey_facetLimit=batch_size,
            speciesKey_facetOffset=offset,
        )

        batch = []
        for facet in result.get("facets", []):
            batch = [(int(item["name"]), item["count"]) for item in facet["counts"]]

        if not batch:
            break

        all_species_counts.extend(batch)
        print(
            f"  Fetched {len(all_species_counts):,} species so far "
            f"(batch min count: {batch[-1][1]:,})"
        )

        if len(batch) < batch_size:
            break
        offset += batch_size

    df = pd.DataFrame(all_species_counts, columns=["species_key", "occurrence_count"])
    df = df.sort_values("occurrence_count", ascending=False).reset_index(drop=True)

    if output_path:
        df.to_csv(output_path, index=False)
        print(f"\nSaved to {output_path}")

    return df


def analyze_distribution(df: pd.DataFrame) -> dict:
    """Analyze the distribution of occurrence counts."""
    counts = df["occurrence_count"]

    analysis = {
        "total_species": len(df),
        "total_occurrences": int(counts.sum()),
        "max_occurrences": int(counts.max()),
        "min_occurrences": int(counts.min()),
        "median_occurrences": int(counts.median()),
        "mean_occurrences": float(counts.mean()),
        "species_with_1": int((counts == 1).sum()),
        "species_with_lte_5": int((counts <= 5).sum()),
        "species_with_lte_10": int((counts <= 10).sum()),
        "species_with_lte_50": int((counts <= 50).sum()),
        "species_with_lte_100": int((counts <= 100).sum()),
        "species_with_lte_1000": int((counts <= 1000).sum()),
    }

    return analysis


def print_analysis(analysis: dict) -> None:
    """Print a formatted analysis summary."""
    print("\n" + "=" * 60)
    print("GBIF Plant Species Occurrence Distribution Analysis")
    print("=" * 60)

    total = analysis["total_species"]
    print(f"\nTotal species with georeferenced records: {total:,}")
    print(f"Total georeferenced occurrences: {analysis['total_occurrences']:,}")

    print("\nOccurrence count statistics:")
    print(f"  Maximum: {analysis['max_occurrences']:,}")
    print(f"  Median:  {analysis['median_occurrences']:,}")
    print(f"  Mean:    {analysis['mean_occurrences']:,.1f}")
    print(f"  Minimum: {analysis['min_occurrences']:,}")

    print("\nData-deficient species breakdown:")
    for threshold, key in [
        (1, "species_with_1"),
        (5, "species_with_lte_5"),
        (10, "species_with_lte_10"),
        (50, "species_with_lte_50"),
        (100, "species_with_lte_100"),
        (1000, "species_with_lte_1000"),
    ]:
        count = analysis[key]
        pct = count / total * 100
        label = f"≤{threshold}" if threshold > 1 else "=1"
        print(f"  {label:>6} occurrences: {count:>8,} species ({pct:>5.1f}%)")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze GBIF occurrence data distribution for plant species"
    )
    parser.add_argument(
        "--test",
        type=str,
        help="Test with a single species (e.g., 'Adansonia digitata')",
    )
    parser.add_argument(
        "--fetch-all",
        action="store_true",
        help="Fetch occurrence counts for all plant species",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("app/public/plant_species_counts.csv"),
        help="Output CSV path (default: app/public/plant_species_counts.csv)",
    )
    parser.add_argument(
        "--from-csv",
        type=Path,
        help="Load existing CSV instead of fetching from GBIF",
    )

    args = parser.parse_args()

    if args.test:
        test_single_species(args.test)
        return

    if args.from_csv:
        print(f"Loading data from {args.from_csv}")
        df = pd.read_csv(args.from_csv)
    elif args.fetch_all:
        df = fetch_all_plant_species_counts(args.output_csv)
    else:
        # Default: test with African Baobab
        test_single_species("Adansonia digitata")
        print("\n" + "-" * 60)
        print("Use --fetch-all to fetch counts for all plant species")
        print("Use --test 'Species name' to test a specific species")
        return

    # Analyze and display results
    analysis = analyze_distribution(df)
    print_analysis(analysis)

    # Save analysis as JSON
    analysis_path = args.output_csv.with_suffix(".json")
    with open(analysis_path, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"\nSaved analysis to {analysis_path}")


if __name__ == "__main__":
    main()
