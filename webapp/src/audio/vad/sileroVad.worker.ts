/// <reference lib="webworker" />

import * as ort from "onnxruntime-web/wasm";
import { SEGMENTATION_CONFIG } from "../segmentation/segmentationConfig";

type PcmChunkMessage = {
  type: "pcm_chunk";
  samples: Float32Array;
  timestampMs: number;
  durationMs: number;
};

type WorkerInbound =
  | { type: "init"; modelUrl: string }
  | PcmChunkMessage
  | { type: "smoke_infer" }
  | { type: "destroy" };

type WorkerOutbound =
  | { type: "ready" }
  | { type: "error"; message: string }
  | {
      type: "frame";
      timestampMs: number;
      durationMs: number;
      speechProbability: number;
    };

let session: ort.InferenceSession | null = null;
let state: ort.Tensor | null = null;
let stateBuffer: Float32Array | null = null;
let sampleRateTensor: ort.Tensor | null = null;
let inferRunning = false;
let pendingChunks: PcmChunkMessage[] = [];

const WINDOW_SIZE = SEGMENTATION_CONFIG.vadWindowSamples;
const inputBuffer = new Float32Array(WINDOW_SIZE);

async function initSession(modelUrl: string): Promise<void> {
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.simd = true;
  ort.env.wasm.proxy = false;

  session = await ort.InferenceSession.create(modelUrl, {
    executionProviders: ["wasm"],
    graphOptimizationLevel: "all",
  });

  stateBuffer = new Float32Array(2 * 1 * 128);
  state = new ort.Tensor("float32", stateBuffer, [2, 1, 128]);
  sampleRateTensor = new ort.Tensor(
    "int64",
    BigInt64Array.from([BigInt(SEGMENTATION_CONFIG.vadSampleRate)]),
    [1],
  );
}

async function runInference(chunk: PcmChunkMessage): Promise<WorkerOutbound> {
  if (!session || !state || !sampleRateTensor || !stateBuffer) {
    return { type: "error", message: "session_not_ready" };
  }

  inputBuffer.fill(0);
  inputBuffer.set(chunk.samples.subarray(0, WINDOW_SIZE));

  const inputTensor = new ort.Tensor("float32", inputBuffer, [1, WINDOW_SIZE]);
  const outputs = await session.run({
    input: inputTensor,
    state,
    sr: sampleRateTensor,
  });

  const outputNames = session.outputNames;
  const probability = Number((outputs[outputNames[0]] as ort.Tensor).data[0]);
  const nextState = outputs[outputNames[1]] as ort.Tensor;
  stateBuffer.set(nextState.data as Float32Array);

  return {
    type: "frame",
    timestampMs: chunk.timestampMs,
    durationMs: chunk.durationMs,
    speechProbability: probability,
  };
}

async function drainInferenceQueue(): Promise<void> {
  if (inferRunning) {
    return;
  }
  inferRunning = true;

  while (pendingChunks.length > 0) {
    const chunk = pendingChunks.shift();
    if (!chunk) {
      continue;
    }
    const response = await runInference(chunk);
    self.postMessage(response);
  }

  inferRunning = false;
}

function enqueueChunk(chunk: PcmChunkMessage): void {
  pendingChunks.push(chunk);
  void drainInferenceQueue();
}

self.onmessage = async (event: MessageEvent<WorkerInbound>) => {
  const message = event.data;
  try {
    if (message.type === "init") {
      await initSession(message.modelUrl);
      const response: WorkerOutbound = { type: "ready" };
      self.postMessage(response);
      return;
    }

    if (message.type === "pcm_chunk") {
      enqueueChunk(message);
      return;
    }

    if (message.type === "smoke_infer") {
      const response = await runInference({
        type: "pcm_chunk",
        samples: new Float32Array(WINDOW_SIZE),
        timestampMs: 0,
        durationMs: SEGMENTATION_CONFIG.vadFrameDurationMs,
      });
      self.postMessage(response);
      return;
    }

    if (message.type === "destroy") {
      pendingChunks = [];
      session = null;
      state = null;
      stateBuffer = null;
      sampleRateTensor = null;
      return;
    }
  } catch (error) {
    const response: WorkerOutbound = {
      type: "error",
      message: error instanceof Error ? error.message : "worker_error",
    };
    self.postMessage(response);
  }
};
