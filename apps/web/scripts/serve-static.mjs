#!/usr/bin/env node
/**
 * Dependency-free static server for the built Storybook.
 *
 * The screenshot suite must be reproducible in CI with nothing fetched at run
 * time, so this is deliberately a few lines of node:http rather than a package.
 *
 * Usage: node scripts/serve-static.mjs <dir> <port>
 */
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import path from "node:path";

const root = path.resolve(process.argv[2] ?? "storybook-static");
const port = Number(process.argv[3] ?? 6100);

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".map": "application/json; charset=utf-8",
};

createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost");
  let filePath = path.join(root, decodeURIComponent(url.pathname));
  // contain the served path inside root
  if (!filePath.startsWith(root)) {
    res.writeHead(403).end("forbidden");
    return;
  }
  if (existsSync(filePath) && statSync(filePath).isDirectory()) {
    filePath = path.join(filePath, "index.html");
  }
  if (!existsSync(filePath)) {
    res.writeHead(404).end("not found");
    return;
  }
  res.writeHead(200, {
    "content-type": TYPES[path.extname(filePath)] ?? "application/octet-stream",
    "cache-control": "no-store",
  });
  createReadStream(filePath).pipe(res);
}).listen(port, () => {
  console.log(`serving ${root} on http://127.0.0.1:${port}`);
});
