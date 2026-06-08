const OGG_CAPTURE_PATTERN = "OggS";
const OPUS_HEAD_MAGIC = "OpusHead";
const OPUS_TAGS_MAGIC = "OpusTags";
const OGG_HEADER_FIXED_SIZE = 27;
const OGG_BOS_FLAG = 0x02;
const OGG_EOS_FLAG = 0x04;
const OGG_GRANULE_RATE_HZ = 48_000n;
const MICROSECONDS_PER_SECOND = 1_000_000n;

export type OggOpusAudioPacket = {
  data: Uint8Array;
  durationUs: number;
};

const textEncoder = new TextEncoder();

const createCrcTable = (): Uint32Array => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index << 24;
    for (let bit = 0; bit < 8; bit += 1) {
      value =
        (value & 0x80000000) !== 0
          ? ((value << 1) ^ 0x04c11db7) >>> 0
          : (value << 1) >>> 0;
    }
    table[index] = value >>> 0;
  }
  return table;
};

const CRC_TABLE = createCrcTable();

const writeAscii = (target: Uint8Array, offset: number, value: string) => {
  target.set(textEncoder.encode(value), offset);
};

const writeUint32LE = (target: Uint8Array, offset: number, value: number) => {
  const view = new DataView(target.buffer, target.byteOffset, target.byteLength);
  view.setUint32(offset, value >>> 0, true);
};

const writeUint64LE = (target: Uint8Array, offset: number, value: bigint) => {
  const normalized = value < 0n ? 0n : value;
  const low = Number(normalized & 0xffffffffn);
  const high = Number((normalized >> 32n) & 0xffffffffn);
  writeUint32LE(target, offset, low);
  writeUint32LE(target, offset + 4, high);
};

const concatUint8Arrays = (parts: Uint8Array[]): Uint8Array => {
  const totalLength = parts.reduce((sum, part) => sum + part.length, 0);
  const merged = new Uint8Array(totalLength);
  let offset = 0;
  for (const part of parts) {
    merged.set(part, offset);
    offset += part.length;
  }
  return merged;
};

const computeOggChecksum = (page: Uint8Array): number => {
  let checksum = 0;
  for (let index = 0; index < page.length; index += 1) {
    checksum =
      ((checksum << 8) ^
        CRC_TABLE[((checksum >>> 24) ^ page[index]) & 0xff]) >>>
      0;
  }
  return checksum >>> 0;
};

const createOggSegments = (packetLength: number): number[] => {
  if (packetLength === 0) {
    return [0];
  }
  const segments: number[] = [];
  let remaining = packetLength;
  while (remaining >= 255) {
    segments.push(255);
    remaining -= 255;
  }
  segments.push(remaining);
  return segments;
};

const createOggPage = ({
  packet,
  headerType,
  granulePosition,
  serialNumber,
  sequenceNumber,
}: {
  packet: Uint8Array;
  headerType: number;
  granulePosition: bigint;
  serialNumber: number;
  sequenceNumber: number;
}): Uint8Array => {
  const lacingValues = createOggSegments(packet.length);
  if (lacingValues.length > 255) {
    throw new Error("ogg_opus_packet_too_large");
  }

  const header = new Uint8Array(OGG_HEADER_FIXED_SIZE + lacingValues.length);
  writeAscii(header, 0, OGG_CAPTURE_PATTERN);
  header[4] = 0;
  header[5] = headerType;
  writeUint64LE(header, 6, granulePosition);
  writeUint32LE(header, 14, serialNumber);
  writeUint32LE(header, 18, sequenceNumber);
  writeUint32LE(header, 22, 0);
  header[26] = lacingValues.length;
  header.set(lacingValues, OGG_HEADER_FIXED_SIZE);

  const page = new Uint8Array(header.length + packet.length);
  page.set(header, 0);
  page.set(packet, header.length);
  writeUint32LE(page, 22, computeOggChecksum(page));
  return page;
};

const buildOpusTagsPacket = (vendorName: string): Uint8Array => {
  const vendorBytes = textEncoder.encode(vendorName);
  const packet = new Uint8Array(8 + 4 + vendorBytes.length + 4);
  writeAscii(packet, 0, OPUS_TAGS_MAGIC);
  writeUint32LE(packet, 8, vendorBytes.length);
  packet.set(vendorBytes, 12);
  writeUint32LE(packet, 12 + vendorBytes.length, 0);
  return packet;
};

const durationUsToGranuleIncrement = (durationUs: number): bigint =>
  (BigInt(Math.max(0, Math.round(durationUs))) * OGG_GRANULE_RATE_HZ +
    MICROSECONDS_PER_SECOND / 2n) /
  MICROSECONDS_PER_SECOND;

export const muxOggOpusFile = ({
  identificationHeader,
  audioPackets,
  vendorName = "Proyecto AI Medico",
}: {
  identificationHeader: Uint8Array;
  audioPackets: OggOpusAudioPacket[];
  vendorName?: string;
}): Uint8Array => {
  if (identificationHeader.length === 0) {
    throw new Error("ogg_opus_missing_identification_header");
  }
  if (!new TextDecoder().decode(identificationHeader.subarray(0, 8)).startsWith(OPUS_HEAD_MAGIC)) {
    throw new Error("ogg_opus_invalid_identification_header");
  }

  const serialSeed = new Uint32Array(1);
  crypto.getRandomValues(serialSeed);
  const serialNumber = serialSeed[0] ?? 1;
  let sequenceNumber = 0;
  let granulePosition = 0n;

  const pages: Uint8Array[] = [];
  pages.push(
    createOggPage({
      packet: identificationHeader,
      headerType: OGG_BOS_FLAG,
      granulePosition,
      serialNumber,
      sequenceNumber,
    }),
  );
  sequenceNumber += 1;

  pages.push(
    createOggPage({
      packet: buildOpusTagsPacket(vendorName),
      headerType: 0,
      granulePosition,
      serialNumber,
      sequenceNumber,
    }),
  );
  sequenceNumber += 1;

  for (let index = 0; index < audioPackets.length; index += 1) {
    const packet = audioPackets[index];
    granulePosition += durationUsToGranuleIncrement(packet.durationUs);
    pages.push(
      createOggPage({
        packet: packet.data,
        headerType: index === audioPackets.length - 1 ? OGG_EOS_FLAG : 0,
        granulePosition,
        serialNumber,
        sequenceNumber,
      }),
    );
    sequenceNumber += 1;
  }

  return concatUint8Arrays(pages);
};
