// Minimal PNG reading and writing for imgdiff.mjs and shoot.mjs. Node only, no packages.
// Reads 8-bit, non-interlaced PNGs of every colour type (what browsers write); writes 8-bit RGB.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

const SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

// Returns { w, h, rgba } or throws an Error with a readable message.
export function decode(file) {
  const buf = fs.readFileSync(file);
  if (buf.length < 8 || !buf.subarray(0, 8).equals(SIG)) throw new Error(`${file} is not a PNG`);
  let pos = 8, w, h, depth, type, interlace, palette, trns;
  const idat = [];
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos);
    const kind = buf.toString('latin1', pos + 4, pos + 8);
    const data = buf.subarray(pos + 8, pos + 8 + len);
    if (kind === 'IHDR') {
      w = data.readUInt32BE(0); h = data.readUInt32BE(4);
      depth = data[8]; type = data[9]; interlace = data[12];
    } else if (kind === 'PLTE') palette = data;
    else if (kind === 'tRNS') trns = data;
    else if (kind === 'IDAT') idat.push(data);
    else if (kind === 'IEND') break;
    pos += 12 + len;
  }
  const bpp = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }[type];
  if (depth !== 8 || !bpp || interlace) throw new Error(`${file}: only 8-bit, non-interlaced PNGs are supported`);
  const stride = w * bpp;
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const px = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)], src = y * (stride + 1) + 1, dst = y * stride, up = dst - stride;
    for (let i = 0; i < stride; i++) {
      const a = i >= bpp ? px[dst + i - bpp] : 0;
      const b = y ? px[up + i] : 0;
      const c = y && i >= bpp ? px[up + i - bpp] : 0;
      let pred = 0;
      if (f === 1) pred = a;
      else if (f === 2) pred = b;
      else if (f === 3) pred = (a + b) >> 1;
      else if (f === 4) {
        const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
        pred = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      }
      px[dst + i] = (raw[src + i] + pred) & 0xff;
    }
  }
  const rgba = Buffer.alloc(w * h * 4);
  for (let p = 0; p < w * h; p++) {
    const s = p * bpp, d = p * 4;
    if (type === 6) px.copy(rgba, d, s, s + 4);
    else if (type === 2) { px.copy(rgba, d, s, s + 3); rgba[d + 3] = 255; }
    else if (type === 0) { rgba.fill(px[s], d, d + 3); rgba[d + 3] = 255; }
    else if (type === 4) { rgba.fill(px[s], d, d + 3); rgba[d + 3] = px[s + 1]; }
    else {
      const i = px[s];
      palette.copy(rgba, d, i * 3, i * 3 + 3);
      rgba[d + 3] = trns && i < trns.length ? trns[i] : 255;
    }
  }
  return { w, h, rgba };
}

const CRC = new Int32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c;
});
function crc32(buf) {
  let c = -1;
  for (const byte of buf) c = CRC[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ -1) >>> 0;
}
function chunk(kind, data) {
  const out = Buffer.alloc(12 + data.length);
  out.writeUInt32BE(data.length, 0);
  out.write(kind, 4, 'latin1');
  data.copy(out, 8);
  out.writeUInt32BE(crc32(out.subarray(4, 8 + data.length)), 8 + data.length);
  return out;
}

// rgb: Buffer of w*h*3 bytes. Returns the PNG file bytes.
export function encodeRGB(w, h, rgb) {
  const rows = Buffer.alloc(h * (w * 3 + 1));
  for (let y = 0; y < h; y++) rgb.copy(rows, y * (w * 3 + 1) + 1, y * w * 3, (y + 1) * w * 3);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([SIG, chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(rows)), chunk('IEND', Buffer.alloc(0))]);
}

// Splits a tall PNG into tileHeight-px slices, outDir/<name>.tile-01.png onwards, so each can be
// read at full size (image viewers for agents scale anything taller than about 2000 px down).
export function writeTiles(file, outDir, tileHeight) {
  const { w, h, rgba } = decode(file);
  const name = path.parse(file).name, files = [];
  fs.mkdirSync(outDir, { recursive: true });
  for (let top = 0, n = 1; top < h; top += tileHeight, n++) {
    const th = Math.min(tileHeight, h - top), rgb = Buffer.alloc(w * th * 3);
    for (let p = 0; p < w * th; p++) rgba.copy(rgb, p * 3, (top * w + p) * 4, (top * w + p) * 4 + 3);
    const out = path.join(outDir, `${name}.tile-${String(n).padStart(2, '0')}.png`);
    fs.writeFileSync(out, encodeRGB(w, th, rgb));
    files.push(out);
  }
  return files;
}
