import { NextRequest, NextResponse } from "next/server";

// Fetch species details from GBIF API
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ key: string }> }
) {
  const { key } = await params;
  const speciesKey = parseInt(key, 10);

  if (isNaN(speciesKey)) {
    return NextResponse.json({ error: "Invalid species key" }, { status: 400 });
  }

  try {
    // Fetch species info from GBIF
    const response = await fetch(`https://api.gbif.org/v1/species/${speciesKey}`);

    if (!response.ok) {
      return NextResponse.json(
        { error: "Species not found in GBIF" },
        { status: 404 }
      );
    }

    const gbifData = await response.json();

    return NextResponse.json({
      key: gbifData.key,
      scientificName: gbifData.scientificName,
      canonicalName: gbifData.canonicalName,
      vernacularName: gbifData.vernacularName,
      kingdom: gbifData.kingdom,
      phylum: gbifData.phylum,
      class: gbifData.class,
      order: gbifData.order,
      family: gbifData.family,
      genus: gbifData.genus,
      species: gbifData.species,
      taxonomicStatus: gbifData.taxonomicStatus,
      gbifUrl: `https://www.gbif.org/species/${speciesKey}`,
    });
  } catch (error) {
    console.error("Error fetching from GBIF:", error);
    return NextResponse.json(
      { error: "Failed to fetch species data" },
      { status: 500 }
    );
  }
}
