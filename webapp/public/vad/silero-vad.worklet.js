/**
 * Captures PCM, downsamples to 16 kHz, and sends 512-sample windows to the VAD worker
 * via MessagePort (bypasses the main thread).
 */
class SileroVadCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {r
      type: "worklet_ready",
      version: this.version,
      sampleRate: this.inputSampleRate,
    });
  }

  appendResampleSample(sample) {
    if (this.resampleLength >= this.resampleBuffer.length) {
      return;
    }r
    this.resampleLength += 1;
  }

  downsampleBlock(inputChannel) {
    let sourceIndex = 0;
    while (sourceIndex < inputChannel.length) {
      const targetIndex = Math.floor(sourceIndex / this.ratio);
      const nextSourceIndex = Math.floor((targetIndex + 1) * this.ratio);
      let sum = 0;
      let count = 0;
      const end = Math.min(nextSourceIndex, inputChannel.length);
      for (let index = Math.floor(sourceIndex); index < end; index += 1) {
        sum += inputChannel[index];
        count += 1;
      }
      if (count > 0) {
        this.appendResampleSample(sum / count);
      }
      sourceIndex = nextSourceIndex;
    }
  }

  emitChunk() {
    const chunk = this.resampleBuffer.slice(0, this.chunkSamples);
    const remaining = this.resampleLength - this.chunkSamples;
    if (remaining > 0) {
      this.resampleBuffer.copyWithin(0, this.chunkSamples, this.resampleLength);
    }
    this.resampleLength = Math.max(0, remaining);

    const timestampMs = (currentTime - this.sessionStart) * 1000;
    this.port.postMessage(
      {
        type: "pcm_chunk",
        samples: chunk,
        timestampMs,
        durationMs: (this.chunkSamples / this.targetSampleRate) * 1000,
      },
      [chunk.buffer],
    );
  }

  process(inputs, outputs) {
    const input = inputs[0];
    const output = outputs[0];
    if (!input || input.length === 0) {
      if (output) {
        for (const channel of output) {
          channel.fill(0);
        }
      }
      return true;
    }

    const channel = input[0];
    if (!channel) {
      if (output) {
        for (const destination of output) {
          destination.fill(0);
        }
      }
      return true;
    }

    if (output) {
      for (let index = 0; index < output.length; index += 1) {
        const destination = output[index];
        destination.set(
          input[Math.min(index, input.length - 1)] ?? channel,
        );
      }
    }

    this.downsampleBlock(channel);

    while (this.resampleLength >= this.chunkSamples) {
      this.emitChunk();
    }

    return true;
  }
}

registerProcessor("silero-vad-capture", SileroVadCaptureProcessor);
