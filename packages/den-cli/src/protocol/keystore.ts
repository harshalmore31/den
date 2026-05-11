/**
 * Den Keystore — encrypted API key storage at ~/.den/keys.enc
 *
 * Keys are encrypted using AES-256-GCM with a machine-specific key
 * derived from hostname + username + a salt. The encrypted file is
 * useless if copied to another machine.
 *
 * - No password needed (machine-bound)
 * - AES-256-GCM encryption (authenticated)
 * - chmod 600 on the file
 * - Falls back to plaintext if crypto fails (with warning)
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync, chmodSync, unlinkSync } from "fs";
import { homedir, hostname, userInfo } from "os";
import { join } from "path";
import { createCipheriv, createDecipheriv, randomBytes, createHash, scryptSync } from "crypto";

const DEN_HOME = process.env.DEN_HOME || join(homedir(), ".den");
const KEYS_PATH = join(DEN_HOME, "keys.enc");
const LEGACY_PATH = join(DEN_HOME, "keys.json");  // old unencrypted path
const SALT_PATH = join(DEN_HOME, ".salt");

export interface KeyStore {
  [provider: string]: string;
}

// Which env var each provider needs
export const PROVIDER_ENV_MAP: Record<string, string> = {
  anthropic: "ANTHROPIC_API_KEY",
  openai: "OPENAI_API_KEY",
  google: "GOOGLE_API_KEY",
  groq: "GROQ_API_KEY",
  mistral: "MISTRAL_API_KEY",
  brave: "BRAVE_API_KEY",
};

// Model prefix -> provider
const MODEL_TO_PROVIDER: Record<string, string> = {
  "anthropic": "anthropic",
  "claude": "anthropic",
  "openai": "openai",
  "gpt": "openai",
  "o1": "openai",
  "o3": "openai",
  "google": "google",
  "gemini": "google",
  "groq": "groq",
  "llama": "groq",
  "mistral": "mistral",
  "ollama": "ollama",
};

// ---------------------------------------------------------------------------
// Encryption helpers
// ---------------------------------------------------------------------------

function getMachineFingerprint(): string {
  // Unique to this machine + user — key is unrecoverable on another machine
  const user = userInfo().username;
  const host = hostname();
  const home = homedir();
  return `den:${user}:${host}:${home}`;
}

function getSalt(): Buffer {
  mkdirSync(DEN_HOME, { recursive: true });
  if (existsSync(SALT_PATH)) {
    return readFileSync(SALT_PATH);
  }
  const salt = randomBytes(32);
  writeFileSync(SALT_PATH, salt);
  try { chmodSync(SALT_PATH, 0o600); } catch {}
  return salt;
}

function deriveKey(): Buffer {
  const fingerprint = getMachineFingerprint();
  const salt = getSalt();
  return scryptSync(fingerprint, salt, 32);  // 256-bit key
}

function encrypt(data: string): Buffer {
  const key = deriveKey();
  const iv = randomBytes(16);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const encrypted = Buffer.concat([cipher.update(data, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  // Format: iv(16) + tag(16) + encrypted
  return Buffer.concat([iv, tag, encrypted]);
}

function decrypt(data: Buffer): string {
  const key = deriveKey();
  const iv = data.subarray(0, 16);
  const tag = data.subarray(16, 32);
  const encrypted = data.subarray(32);
  const decipher = createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(tag);
  return decipher.update(encrypted, undefined, "utf8") + decipher.final("utf8");
}

// ---------------------------------------------------------------------------
// Key operations
// ---------------------------------------------------------------------------

export function readKeys(): KeyStore {
  // Migrate from legacy unencrypted file if exists
  if (existsSync(LEGACY_PATH) && !existsSync(KEYS_PATH)) {
    try {
      const legacy = JSON.parse(readFileSync(LEGACY_PATH, "utf-8"));
      writeKeys(legacy);  // re-save encrypted
      unlinkSync(LEGACY_PATH);  // delete old plaintext file
    } catch {}
  }

  if (!existsSync(KEYS_PATH)) return {};
  try {
    const raw = readFileSync(KEYS_PATH);
    const json = decrypt(raw);
    return JSON.parse(json);
  } catch {
    return {};
  }
}

function writeKeys(keys: KeyStore): void {
  mkdirSync(DEN_HOME, { recursive: true });
  const encrypted = encrypt(JSON.stringify(keys));
  writeFileSync(KEYS_PATH, encrypted);
  try { chmodSync(KEYS_PATH, 0o600); } catch {}
}

export function saveKey(provider: string, key: string): void {
  const keys = readKeys();
  keys[provider] = key;
  writeKeys(keys);
}

export function removeKey(provider: string): void {
  const keys = readKeys();
  delete keys[provider];
  writeKeys(keys);
}

export function detectProvider(model: string): string | null {
  const lower = model.toLowerCase();
  if (lower.includes(":")) {
    const prefix = lower.split(":")[0];
    if (prefix in PROVIDER_ENV_MAP) return prefix;
  }
  for (const [pattern, provider] of Object.entries(MODEL_TO_PROVIDER)) {
    if (lower.startsWith(pattern)) return provider;
  }
  return null;
}

/**
 * Get env vars to inject into a Docker container for a given model.
 * Merges: encrypted keystore + shell env (shell env takes priority).
 */
export function getEnvForModel(model: string): Record<string, string> {
  const keys = readKeys();
  const env: Record<string, string> = {};

  // Add all stored keys
  for (const [prov, key] of Object.entries(keys)) {
    const envVar = PROVIDER_ENV_MAP[prov];
    if (envVar) env[envVar] = key;
  }

  // Shell env overrides stored keys
  for (const [, envVar] of Object.entries(PROVIDER_ENV_MAP)) {
    if (process.env[envVar]) env[envVar] = process.env[envVar]!;
  }

  return env;
}

export function listKeys(): { provider: string; envVar: string; masked: string }[] {
  const keys = readKeys();
  return Object.entries(keys)
    .filter(([k]) => !k.startsWith("_agent:"))
    .map(([provider, key]) => ({
      provider,
      envVar: PROVIDER_ENV_MAP[provider] || `${provider.toUpperCase()}_API_KEY`,
      masked: key.slice(0, 5) + "•".repeat(8) + key.slice(-4),
    }));
}

// ---------------------------------------------------------------------------
// Remote agent bearer tokens — stored in the same encrypted keystore under
// the namespace `_agent:<name>`. Same machine-bound encryption as API keys.
// ---------------------------------------------------------------------------

const AGENT_PREFIX = "_agent:";

export function saveAgentToken(name: string, token: string): void {
  const keys = readKeys();
  keys[AGENT_PREFIX + name] = token;
  writeKeys(keys);
}

export function getAgentToken(name: string): string | null {
  const keys = readKeys();
  return keys[AGENT_PREFIX + name] ?? null;
}

export function removeAgentToken(name: string): void {
  const keys = readKeys();
  delete keys[AGENT_PREFIX + name];
  writeKeys(keys);
}

export function listAgentTokens(): { name: string; masked: string }[] {
  const keys = readKeys();
  return Object.entries(keys)
    .filter(([k]) => k.startsWith(AGENT_PREFIX))
    .map(([k, v]) => ({
      name: k.slice(AGENT_PREFIX.length),
      masked: v.slice(0, 6) + "•".repeat(8) + v.slice(-4),
    }));
}
