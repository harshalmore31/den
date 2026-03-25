/**
 * Docker utilities for Den CLI.
 *
 * Handles image pulling, container management, and Docker checks.
 */

import { execSync } from "child_process";

const DEFAULT_IMAGE = "harshalmore31/den:latest";

/**
 * Check if Docker is installed and running.
 */
export function checkDocker(): { ok: boolean; error?: string } {
  try {
    execSync("docker info", { stdio: "ignore", timeout: 5000 });
    return { ok: true };
  } catch {
    try {
      execSync("docker --version", { stdio: "ignore" });
      return { ok: false, error: "Docker is installed but not running. Start Docker Desktop." };
    } catch {
      return { ok: false, error: "Docker is not installed. Get it at https://docker.com" };
    }
  }
}

/**
 * Check if the Den base image exists locally.
 */
export function imageExists(image: string = DEFAULT_IMAGE): boolean {
  try {
    execSync(`docker image inspect ${image}`, { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

/**
 * Pull the Den base image from registry.
 */
export function pullImage(image: string = DEFAULT_IMAGE): boolean {
  try {
    execSync(`docker pull ${image}`, { stdio: "inherit", timeout: 300000 });
    return true;
  } catch {
    return false;
  }
}

/**
 * Ensure the Den image is available — pull if needed.
 */
export function ensureImage(image: string = DEFAULT_IMAGE): { ok: boolean; error?: string } {
  // Check local first
  if (imageExists(image)) return { ok: true };

  // Also check den/base:latest (local build)
  if (imageExists("den/base:latest")) return { ok: true };

  // Pull from registry
  console.log(`  Pulling Den image: ${image}...`);
  if (pullImage(image)) return { ok: true };

  return {
    ok: false,
    error: `Failed to pull ${image}. Build locally with:\n  cd Den && docker build -f images/base/Dockerfile -t den/base:latest .`,
  };
}

/**
 * Get the best available image name.
 */
export function getImageName(preferred?: string): string {
  if (preferred && imageExists(preferred)) return preferred;
  if (imageExists(DEFAULT_IMAGE)) return DEFAULT_IMAGE;
  if (imageExists("den/base:latest")) return "den/base:latest";
  return DEFAULT_IMAGE; // will trigger pull
}

export { DEFAULT_IMAGE };
