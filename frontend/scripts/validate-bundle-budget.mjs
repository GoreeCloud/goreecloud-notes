import { readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";

const maxJavaScriptChunkBytes = 500_000;
const assetsDirectory = resolve("dist/assets");
const javascriptAssets = readdirSync(assetsDirectory)
  .filter((name) => name.endsWith(".js"))
  .map((name) => ({ name, bytes: statSync(resolve(assetsDirectory, name)).size }));

if (javascriptAssets.length === 0) {
  throw new Error("No production JavaScript assets were emitted for bundle-budget validation.");
}

const oversized = javascriptAssets.filter((asset) => asset.bytes > maxJavaScriptChunkBytes);
if (oversized.length > 0) {
  const details = oversized.map((asset) => `${asset.name}=${asset.bytes}B`).join(", ");
  throw new Error(`JavaScript chunk budget exceeded (${maxJavaScriptChunkBytes}B): ${details}`);
}

const largest = [...javascriptAssets].sort((left, right) => right.bytes - left.bytes)[0];
console.log(
  `Production bundle budget validated across ${javascriptAssets.length} JavaScript chunks; largest ${largest.name}=${largest.bytes}B.`,
);
