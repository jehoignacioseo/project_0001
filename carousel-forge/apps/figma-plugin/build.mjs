/**
 * 플러그인 번들.
 *
 * Figma 샌드박스는 모듈을 이해하지 못하므로 한 파일로 묶어야 한다. UI는
 * `__html__`로 주입되는 단일 HTML이라 그대로 복사한다.
 */

import { cpSync, mkdirSync } from "node:fs";
import { build, context } from "esbuild";

const watch = process.argv.includes("--watch");

const options = {
  entryPoints: ["src/code.ts"],
  bundle: true,
  outfile: "dist/code.js",
  target: "es2017",       // Figma 샌드박스(QuickJS)가 읽는 수준
  format: "iife",
  logLevel: "info",
};

mkdirSync("dist", { recursive: true });
cpSync("src/ui.html", "dist/ui.html");

if (watch) {
  const ctx = await context(options);
  await ctx.watch();
  console.log("watching…");
} else {
  await build(options);
  console.log("dist/code.js, dist/ui.html");
}
