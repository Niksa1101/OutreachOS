#!/usr/bin/env node
/**
 * Generate the placeholder application icon.
 *
 * Tech.md §2 calls the icon a "placeholder, replaceable". A generator is
 * checked in rather than only its output so that "what is this icon" has an
 * answer that is not "someone drew it once" — and so the palette stays tied to
 * the same accent value the design tokens use (Q27 / Q123).
 *
 * `tauri-build` embeds `icons/icon.ico` as a Win32 resource at build time, so
 * this must run before the first `cargo build`. It is not wired into any CI
 * step because its output is committed and never changes on its own.
 *
 *   node scripts/gen-placeholder-icon.mjs
 */

import { deflateSync } from 'node:zlib';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT_DIR = join(REPO_ROOT, 'src-tauri', 'icons');

// oklch(0.58 0.15 255) converted to sRGB — the accent from ADR-0001, and the
// reason this file exists next to the tokens rather than in a design folder.
const ACCENT = [0x33, 0x7b, 0xd0];
// zinc-950, the token layer's --color-bg.
const BACKDROP = [0x09, 0x09, 0x0b];

/* -------------------------------------------------------------------------- */
/* Drawing                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Render the mark at an arbitrary size into a straight-alpha RGBA buffer.
 *
 * A dark rounded square carrying an accent ring. Deliberately trivial: an
 * elaborate placeholder is one nobody replaces.
 *
 * @param {number} size
 * @returns {Buffer} RGBA, `size * size * 4` bytes
 */
function renderRgba(size) {
  const px = Buffer.alloc(size * size * 4);
  const radius = size * 0.22;
  const cx = (size - 1) / 2;
  const cy = (size - 1) / 2;
  const ringOuter = size * 0.32;
  const ringInner = size * 0.19;

  // 3x3 supersampling. At 16px an aliased ring reads as a grey blob.
  const S = 3;

  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      let inSquare = 0;
      let inRing = 0;

      for (let sy = 0; sy < S; sy += 1) {
        for (let sx = 0; sx < S; sx += 1) {
          const px1 = x + (sx + 0.5) / S;
          const py1 = y + (sy + 0.5) / S;

          if (insideRoundedSquare(px1, py1, size, radius)) inSquare += 1;

          const d = Math.hypot(px1 - cx - 0.5, py1 - cy - 0.5);
          if (d <= ringOuter && d >= ringInner) inRing += 1;
        }
      }

      const total = S * S;
      const squareCoverage = inSquare / total;
      const ringCoverage = (inRing / total) * squareCoverage;

      const offset = (y * size + x) * 4;
      // Composite the ring over the backdrop, then carry the square's coverage
      // as the alpha channel so the corners are genuinely transparent.
      for (let c = 0; c < 3; c += 1) {
        const base = BACKDROP[c] ?? 0;
        const over = ACCENT[c] ?? 0;
        px[offset + c] = Math.round(base * (1 - ringCoverage) + over * ringCoverage);
      }
      px[offset + 3] = Math.round(squareCoverage * 255);
    }
  }

  return px;
}

/** @returns {boolean} */
function insideRoundedSquare(x, y, size, radius) {
  const min = 0;
  const max = size;
  if (x < min || y < min || x > max || y > max) return false;

  const dx = Math.max(min + radius - x, 0, x - (max - radius));
  const dy = Math.max(min + radius - y, 0, y - (max - radius));
  if (dx === 0 || dy === 0) return true;
  return Math.hypot(dx, dy) <= radius;
}

/* -------------------------------------------------------------------------- */
/* PNG                                                                         */
/* -------------------------------------------------------------------------- */

const CRC_TABLE = (() => {
  const table = new Int32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c;
  }
  return table;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i += 1) {
    c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const head = Buffer.alloc(8);
  head.writeUInt32BE(data.length, 0);
  head.write(type, 4, 'ascii');
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), data])), 0);
  return Buffer.concat([head, data, crc]);
}

/** @returns {Buffer} a complete PNG file */
function encodePng(rgba, size) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // colour type: RGBA
  ihdr[10] = 0; // deflate
  ihdr[11] = 0; // adaptive filtering
  ihdr[12] = 0; // no interlace

  // Filter type 0 on every scanline. The image is tiny and mostly flat; a
  // filter search would save bytes nobody is counting.
  const stride = size * 4;
  const raw = Buffer.alloc((stride + 1) * size);
  for (let y = 0; y < size; y += 1) {
    raw[y * (stride + 1)] = 0;
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  }

  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

/* -------------------------------------------------------------------------- */
/* ICO                                                                         */
/* -------------------------------------------------------------------------- */

/**
 * Classic BMP-in-ICO entry: BITMAPINFOHEADER with a doubled height, 32bpp BGRA
 * rows bottom-up, then a 1bpp AND mask.
 *
 * The alpha channel makes the mask redundant on every parser written this
 * century, but it is not optional in the format and omitting it produces an
 * icon that renders correctly in Explorer and as a black box in the taskbar.
 */
function encodeIcoBmp(rgba, size) {
  const header = Buffer.alloc(40);
  header.writeUInt32LE(40, 0);
  header.writeInt32LE(size, 4);
  header.writeInt32LE(size * 2, 8);
  header.writeUInt16LE(1, 12); // planes
  header.writeUInt16LE(32, 14); // bpp
  header.writeUInt32LE(0, 16); // BI_RGB

  const xor = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y += 1) {
    const src = (size - 1 - y) * size * 4;
    for (let x = 0; x < size; x += 1) {
      const s = src + x * 4;
      const d = (y * size + x) * 4;
      xor[d] = rgba[s + 2];
      xor[d + 1] = rgba[s + 1];
      xor[d + 2] = rgba[s];
      xor[d + 3] = rgba[s + 3];
    }
  }

  const maskStride = Math.ceil(size / 32) * 4;
  const and = Buffer.alloc(maskStride * size); // all zero: "use the XOR pixel"

  return Buffer.concat([header, xor, and]);
}

function encodeIco(entries) {
  const dir = Buffer.alloc(6);
  dir.writeUInt16LE(0, 0);
  dir.writeUInt16LE(1, 2); // ICO
  dir.writeUInt16LE(entries.length, 4);

  let offset = 6 + entries.length * 16;
  const table = [];
  const blobs = [];

  for (const { size, data } of entries) {
    const entry = Buffer.alloc(16);
    entry[0] = size >= 256 ? 0 : size;
    entry[1] = size >= 256 ? 0 : size;
    entry[2] = 0; // palette size
    entry[3] = 0; // reserved
    entry.writeUInt16LE(1, 4); // planes
    entry.writeUInt16LE(32, 6); // bpp
    entry.writeUInt32LE(data.length, 8);
    entry.writeUInt32LE(offset, 12);
    table.push(entry);
    blobs.push(data);
    offset += data.length;
  }

  return Buffer.concat([dir, ...table, ...blobs]);
}

/* -------------------------------------------------------------------------- */

mkdirSync(OUT_DIR, { recursive: true });

const cache = new Map();
const rgbaFor = (size) => {
  if (!cache.has(size)) cache.set(size, renderRgba(size));
  return cache.get(size);
};

for (const [name, size] of [
  ['32x32.png', 32],
  ['128x128.png', 128],
  ['128x128@2x.png', 256],
  ['icon.png', 512],
]) {
  const file = join(OUT_DIR, name);
  writeFileSync(file, encodePng(rgbaFor(size), size));
  console.log(`icon: wrote ${name} (${size}x${size})`);
}

// 16/32/48 as BMP for maximum parser compatibility; 128/256 as PNG so the file
// stays under 100 KB instead of over 300 KB.
const ico = encodeIco([
  { size: 16, data: encodeIcoBmp(rgbaFor(16), 16) },
  { size: 32, data: encodeIcoBmp(rgbaFor(32), 32) },
  { size: 48, data: encodeIcoBmp(rgbaFor(48), 48) },
  { size: 128, data: encodePng(rgbaFor(128), 128) },
  { size: 256, data: encodePng(rgbaFor(256), 256) },
]);
writeFileSync(join(OUT_DIR, 'icon.ico'), ico);
console.log(`icon: wrote icon.ico (${ico.length} bytes, 5 entries)`);
