// Build script for den-agent CLI.
//
// Goal: produce a single self-contained dist/cli.mjs that runs anywhere
// without needing node_modules. Bundling all deps inline so a user
// installing den-agent into a project with its own React/Ink can't run
// into peer-dep hoisting conflicts.
//
// Three subtle bits:
//   1. ink statically imports react-devtools-core which we don't ship
//      (peer-dep conflicts, dev-only). Alias it to a no-op stub.
//   2. Several CJS deps (signal-exit etc.) use dynamic require() to load
//      Node built-ins. ESM bundles can't, so we inject createRequire in
//      the banner to provide a real `require` global.
//   3. The shebang must appear once at the top so Unix can exec it.

import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");

await build({
  entryPoints: [path.join(root, "src/index.tsx")],
  outfile: path.join(root, "dist/cli.mjs"),
  bundle: true,
  platform: "node",
  target: "node18",
  format: "esm",
  alias: {
    "react-devtools-core": path.join(here, "stub-react-devtools-core.mjs"),
  },
  // Make CommonJS dynamic require() work in this ESM bundle.
  // Some deps (signal-exit, etc.) call require('assert') etc. at module
  // load -- without this they crash with "Dynamic require of X not supported".
  banner: {
    js: [
      "#!/usr/bin/env node",
      "import { createRequire as __createDenRequire } from 'node:module';",
      "const require = __createDenRequire(import.meta.url);",
    ].join("\n"),
  },
  logLevel: "info",
});
