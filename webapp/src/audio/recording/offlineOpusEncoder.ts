import { muxOggOpusFile, type OggOpusAudioPacket } from "./oggOpusMuxer";

const TARGET_SAMPLE_RATE = 16_000;
const DEFAULT_BITRATE_KBPS = 24;
const FRAME_DURATION_US = 20_000;
const FRAME_SAMPLES = (TARGET_SAMPLE_RATE * FRAME_DURATION_US) / 1_000_000;

const normalizeBasePath = (value: string): string => {
  if (!value) {
    return "/";
  }
  return value.endsWith("/") ? value : `${value}/`;
};

const OPUS_RECORDER_ENCODER_URL = `${normalizeBasePath(
  import.meta.env.BASE_URL,
)}opus-recorder/encoderWorker.min.js`;

type OpusEncoderBackend = "webcodecs" | "opus-recorder";

type OpusAudioEncoderConfig = AudioEncoderConfig & {
  opus?: {
    application?: "audio" | "voip" | "lowdelay";
    complexity?: number;
    format?: "opus" | "ogg";
    frameDuration?: number;
    signal?: "auto" | "music" | "voice";
    usedtx?: boolean;
    useinbandfec?: boolean;
  };
};

type EncodedAudioChunkMetadataLike = {
  decoderConfig?: {
    description?: AllowSharedBufferSource;
  };
};

type OpusEncodingResult = {
  blob: Blob;
  encoderBackend: OpusEncoderBackend;
  fallbackReason: string | null;
};

let webCodecsSupportPromise: Promise<boolean> | null = null;

const toUint8Array = (value: AllowSharedBufferSource): Uint8Array => {
  if (value instanceof ArrayBuffer) {
    return new Uint8Array(value.slice(0));
  }
  if (ArrayBuffer.isView(value)) {
    return new Uint8Array(
      value.buffer.slice(
        value.byteOffset,
        value.byteOffset + value.byteLength,
      ),
    );
  }
  const SharedArrayBufferCtor = globalThis.SharedArrayBuffer;
  if (
    typeof SharedArrayBufferCtor !== "undefined" &&
    (value as object) instanceof SharedArrayBufferCtor
  ) {
    return new Uint8Array(value).slice();
  }
  throw new Error("unsupported_buffer_source");
};

const buildWebCodecsConfig = (bitrateKbps: number): OpusAudioEncoderConfig => ({
  codec: "opus",
  sampleRate: TARGET_SAMPLE_RATE,
  numberOfChannels: 1,
  bitrate: bitrateKbps * 1000,
  bitrateMode: "variable",
  opus: {
    application: "voip",
    complexity: 9,
    format: "ogg",
    frameDuration: FRAME_DURATION_US,
    signal: "voice",
    usedtx: false,
    useinbandfec: false,
  },
});

const canUseWebCodecsOpus = async (): Promise<boolean> => {
  if (!webCodecsSupportPromise) {
    webCodecsSupportPromise = (async () => {
      if (
        typeof AudioEncoder === "undefined" ||
        typeof AudioData === "undefined" ||
        typeof AudioEncoder.isConfigSupported !== "function"
      ) {
        return false;
      }

      try {
        const support = await AudioEncoder.isConfigSupported(
          buildWebCodecsConfig(DEFAULT_BITRATE_KBPS),
        );
        return Boolean(support.supported);
      } catch {
        return false;
      }
    })();
  }
  return webCodecsSupportPromise;
};

const encodeWithWebCodecs = async (
  samples: Float32Array,
  bitrateKbps: number,
): Promise<Blob> => {
  const packets: OggOpusAudioPacket[] = [];
  let identificationHeader: Uint8Array | null = null;

  const encoder = new AudioEncoder({
    output: (chunk, metadata) => {
      const packetBytes = new Uint8Array(chunk.byteLength);
      chunk.copyTo(packetBytes);
      packets.push({
        data: packetBytes,
        durationUs: chunk.duration || FRAME_DURATION_US,
      });

      const decoderDescription = (
        metadata as EncodedAudioChunkMetadataLike | undefined
      )?.decoderConfig?.description;
      if (!identificationHeader && decoderDescription) {
        identificationHeader = toUint8Array(decoderDescription);
      }
    },
    error: (error) => {
      throw error;
    },
  });

  try {
    encoder.configure(buildWebCodecsConfig(bitrateKbps));

    for (
      let sampleOffset = 0, frameIndex = 0;
      sampleOffset < samples.length;
      sampleOffset += FRAME_SAMPLES, frameIndex += 1
    ) {
      const frameSamples = new Float32Array(FRAME_SAMPLES);
      frameSamples.set(samples.subarray(sampleOffset, sampleOffset + FRAME_SAMPLES));
      const audioData = new AudioData({
        data: frameSamples,
        format: "f32-planar",
        numberOfChannels: 1,
        numberOfFrames: FRAME_SAMPLES,
        sampleRate: TARGET_SAMPLE_RATE,
        timestamp: frameIndex * FRAME_DURATION_US,
      });
      try {
        encoder.encode(audioData);
      } finally {
        audioData.close();
      }
    }

    await encoder.flush();
  } finally {
    encoder.close();
  }

  if (!identificationHeader || packets.length === 0) {
    throw new Error("webcodecs_opus_missing_stream_metadata");
  }

  const oggBytes = muxOggOpusFile({
    identificationHeader,
    audioPackets: packets,
  });
  return new Blob([oggBytes], { type: "audio/ogg;codecs=opus" });
};

const concatPages = (pages: Uint8Array[]): Uint8Array => {
  const totalLength = pages.reduce((sum, page) => sum + page.length, 0);
  const merged = new Uint8Array(totalLength);
  let offset = 0;
  for (const page of pages) {
    merged.set(page, offset);
    offset += page.length;
  }
  return merged;
};

const chunkMonoSamples = (
  samples: Float32Array,
  chunkSize = 4096,
): Float32Array[] => {
  const chunks: Float32Array[] = [];
  for (let offset = 0; offset < samples.length; offset += chunkSize) {
    chunks.push(samples.slice(offset, offset + chunkSize));
  }
  return chunks;
};

const encodeWithOpusRecorderWorker = async (
  samples: Float32Array,
  bitrateKbps: number,
): Promise<Blob> => {
  const worker = new Worker(OPUS_RECORDER_ENCODER_URL);
  const pages: Uint8Array[] = [];

  try {
    await new Promise<void>((resolve, reject) => {
      let done = false;

      const cleanup = () => {
        worker.onmessage = null;
        worker.onerror = null;
      };

      worker.onerror = (event) => {
        cleanup();
        reject(
          event.error instanceof Error
            ? event.error
            : new Error(event.message || "opus_recorder_worker_error"),
        );
      };

      worker.onmessage = ({ data }) => {
        if (!data || typeof data !== "object") {
          return;
        }

        if (data.message === "ready") {
          worker.postMessage({ command: "getHeaderPages" });
          for (const chunk of chunkMonoSamples(samples)) {
            worker.postMessage(
              { command: "encode", buffers: [chunk] },
              [chunk.buffer],
            );
          }
          worker.postMessage({ command: "done" });
          return;
        }

        if (data.message === "page" && data.page instanceof Uint8Array) {
          pages.push(data.page);
          return;
        }

        if (data.message === "done") {
          done = true;
          cleanup();
          resolve();
        }
      };

      worker.postMessage({
        command: "init",
        encoderApplication: 2048,
        encoderBitRate: bitrateKbps * 1000,
        encoderFrameSize: FRAME_DURATION_US / 1000,
        encoderSampleRate: TARGET_SAMPLE_RATE,
        maxFramesPerPage: 40,
        numberOfChannels: 1,
        originalSampleRate: TARGET_SAMPLE_RATE,
        originalSampleRateOverride: TARGET_SAMPLE_RATE,
        resampleQuality: 0,
        streamPages: false,
      });

      queueMicrotask(() => {
        if (!done && samples.length === 0) {
          worker.postMessage({ command: "done" });
        }
      });
    });
  } finally {
    worker.terminate();
  }

  return new Blob([concatPages(pages)], { type: "audio/ogg;codecs=opus" });
};

export type FrontendOpusEncodingDebug = {
  encoderBackend: OpusEncoderBackend;
  fallbackReason: string | null;
};

export const encodeMono16kToOpusBlob = async (
  samples: Float32Array,
  bitrateKbps = DEFAULT_BITRATE_KBPS,
): Promise<OpusEncodingResult> => {
  if (samples.length === 0) {
    return {
      blob: new Blob([], { type: "audio/ogg;codecs=opus" }),
      encoderBackend: "webcodecs",
      fallbackReason: null,
    };
  }

  if (await canUseWebCodecsOpus()) {
    try {
      return {
        blob: await encodeWithWebCodecs(samples, bitrateKbps),
        encoderBackend: "webcodecs",
        fallbackReason: null,
      };
    } catch (error) {
      return {
        blob: await encodeWithOpusRecorderWorker(samples, bitrateKbps),
        encoderBackend: "opus-recorder",
        fallbackReason:
          error instanceof Error ? error.message : "webcodecs_failed",
      };
    }
  }

  return {
    blob: await encodeWithOpusRecorderWorker(samples, bitrateKbps),
    encoderBackend: "opus-recorder",
    fallbackReason: "webcodecs_unavailable",
  };
};
