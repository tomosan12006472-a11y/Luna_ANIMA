import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const tokenPattern = /["']([^"']+\.js)\?v=([^"']+)["']/g;

function collectFiles(dir, predicate) {
  if (!existsSync(dir)) return [];
  const entries = readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectFiles(fullPath, predicate));
    } else if (entry.isFile() && predicate(fullPath)) {
      files.push(fullPath);
    }
  }
  return files;
}

function relative(file) {
  return path.relative(root, file).replaceAll(path.sep, "/");
}

const files = [
  path.join(root, "app", "static", "index.html"),
  path.join(root, "app", "static", "app.js"),
  ...collectFiles(path.join(root, "app", "static", "js"), (file) => file.endsWith(".js")),
].filter((file) => existsSync(file)).sort((left, right) => left.localeCompare(right));

const records = [];
const required = {
  "app/static/index.html": false,
  "app/static/app.js": false,
};

for (const file of files) {
  const name = relative(file);
  const content = readFileSync(file, "utf8");
  for (const match of content.matchAll(tokenPattern)) {
    const specifier = match[1];
    const token = match[2];
    if (specifier === "/static/ui.js") {
      continue;
    }
    records.push({ file: name, specifier, token });
    if (name === "app/static/index.html" && specifier === "/static/app.js") {
      required[name] = true;
    }
    if (name === "app/static/app.js" && specifier === "/static/js/main.js") {
      required[name] = true;
    }
  }
}

const missing = Object.entries(required)
  .filter(([, found]) => !found)
  .map(([file]) => file);

if (missing.length) {
  console.error(`missing required static import token: ${missing.join(", ")}`);
  process.exit(1);
}

const tokens = new Set(records.map((record) => record.token));
if (tokens.size > 1) {
  console.error("static import token mismatch:");
  for (const record of records) {
    console.error(`- ${record.file}: ${record.specifier}?v=${record.token}`);
  }
  process.exit(1);
}

console.log(`checked ${records.length} static import tokens: ${[...tokens][0] || "none"}`);
