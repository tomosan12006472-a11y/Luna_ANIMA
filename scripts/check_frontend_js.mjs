import { spawnSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const staticApp = path.join(root, "app", "static", "app.js");
const staticJsDir = path.join(root, "app", "static", "js");

function collectJsFiles(dir) {
  if (!existsSync(dir)) return [];
  const entries = readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectJsFiles(fullPath));
    } else if (entry.isFile() && entry.name.endsWith(".js")) {
      files.push(fullPath);
    }
  }
  return files;
}

const files = [staticApp, ...collectJsFiles(staticJsDir)]
  .filter((file) => existsSync(file))
  .sort((left, right) => left.localeCompare(right));

let failed = false;
for (const file of files) {
  const relativePath = path.relative(root, file).replaceAll(path.sep, "/");
  const result = spawnSync(process.execPath, ["--check", file], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.status !== 0) {
    failed = true;
    console.error(`node --check failed: ${relativePath}`);
    if (result.stdout) process.stdout.write(result.stdout);
    if (result.stderr) process.stderr.write(result.stderr);
  }
}

if (failed) {
  process.exit(1);
}

console.log(`checked ${files.length} files`);
