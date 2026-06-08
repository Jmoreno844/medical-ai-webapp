import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const webappRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(webappRoot, "..");
const vadTargetDir = path.join(webappRoot, "public", "vad");
const opusRecorderTargetDir = path.join(webappRoot, "public", "opus-recorder");
const onnxSource = path.join(
  repoRoot,
  "transcription_worker",
  "models",
  "silero_vad.onnx",
);
const opusRecorderWorkerSource = path.join(
  webappRoot,
  "node_modules",
  "opus-recorder",
  "dist",
  "encoderWorker.min.js",
);

mkdirSync(vadTargetDir, { recursive: true });
mkdirSync(opusRecorderTargetDir, { recursive: true });

if (!existsSync(onnxSource)) {
  console.error(`Missing Silero model at ${onnxSource}`);
  process.exit(1);
}
if (!existsSync(opusRecorderWorkerSource)) {
  console.error(`Missing opus-recorder worker at ${opusRecorderWorkerSource}`);
  process.exit(1);
}

copyFileSync(onnxSource, path.join(vadTargetDir, "silero_vad.onnx"));
copyFileSync(
  opusRecorderWorkerSource,
  path.join(opusRecorderTargetDir, "encoderWorker.min.js"),
);

console.log(`VAD assets copied to ${vadTargetDir}`);
console.log(`opus-recorder assets copied to ${opusRecorderTargetDir}`);
console.log(
  "ONNX Runtime WASM is bundled via onnxruntime-web/wasm in the VAD worker. The Opus fallback worker is served from /opus-recorder.",
);
