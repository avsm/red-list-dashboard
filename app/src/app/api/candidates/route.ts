import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

interface CandidateFeature {
  type: "Feature";
  properties: {
    probability: number;
    model_type: string;
  };
  geometry: {
    type: "Point";
    coordinates: [number, number]; // [lon, lat]
  };
}

interface CandidatesGeoJSON {
  type: "FeatureCollection";
  features: CandidateFeature[];
  metadata?: {
    bbox: number[];
    resolution: number;
    probability_threshold: number;
    total_grid_points: number;
    valid_grid_points: number;
    n_candidates: number;
  };
}

// Cache for loaded candidate files
const candidateCache: Record<string, CandidatesGeoJSON> = {};

async function loadCandidates(species: string): Promise<CandidatesGeoJSON | null> {
  const cacheKey = species.toLowerCase().replace(/\s+/g, "_");

  if (candidateCache[cacheKey]) {
    return candidateCache[cacheKey];
  }

  // Look for candidate file in output/{species}/ directory
  const outputDir = path.join(process.cwd(), "..", "output", cacheKey);
  const filePath = path.join(outputDir, "candidates.geojson");

  try {
    const content = await fs.readFile(filePath, "utf-8");
    const geojson = JSON.parse(content) as CandidatesGeoJSON;
    candidateCache[cacheKey] = geojson;
    return geojson;
  } catch {
    return null;
  }
}

async function listAvailableSpecies(): Promise<string[]> {
  const outputDir = path.join(process.cwd(), "..", "output");

  try {
    const dirs = await fs.readdir(outputDir);
    const speciesWithCandidates: string[] = [];

    for (const dir of dirs) {
      const candidatesPath = path.join(outputDir, dir, "candidates.geojson");
      try {
        await fs.access(candidatesPath);
        // Convert quercus_robur -> Quercus Robur
        const name = dir.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
        speciesWithCandidates.push(name);
      } catch {
        // No candidates file in this directory
      }
    }

    return speciesWithCandidates;
  } catch {
    return [];
  }
}

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const species = searchParams.get("species");
  const minProb = parseFloat(searchParams.get("minProb") || "0");

  // If no species specified, list available species
  if (!species) {
    const available = await listAvailableSpecies();
    return NextResponse.json({
      available,
      message: "Specify ?species=<name> to get candidate locations"
    });
  }

  const candidates = await loadCandidates(species);

  if (!candidates) {
    return NextResponse.json(
      { error: `No candidate data found for species: ${species}` },
      { status: 404 }
    );
  }

  // Filter by minimum probability if specified
  let features = candidates.features;
  if (minProb > 0) {
    features = features.filter(f => f.properties.probability >= minProb);
  }

  return NextResponse.json({
    type: "FeatureCollection",
    features,
    metadata: {
      ...candidates.metadata,
      species,
      filtered_count: features.length,
    }
  });
}
