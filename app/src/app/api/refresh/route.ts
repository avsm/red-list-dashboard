import { NextResponse } from "next/server";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";

const execAsync = promisify(exec);

export async function POST() {
  try {
    // Run the Python script from the project root
    const projectRoot = path.join(process.cwd(), "..");
    const { stdout, stderr } = await execAsync(
      "uv run python main.py --fetch-all",
      {
        cwd: projectRoot,
        timeout: 600000, // 10 minute timeout
      }
    );

    return NextResponse.json({
      success: true,
      message: "Data refresh completed",
      output: stdout,
      errors: stderr || null,
    });
  } catch (error) {
    console.error("Error running refresh script:", error);
    return NextResponse.json(
      {
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}
