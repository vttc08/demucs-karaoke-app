class CdgRenderer {
  constructor(canvas) {
    this.width = 300;
    this.height = 216;
    this.canvas = canvas;
    this.canvas.width = this.width;
    this.canvas.height = this.height;
    this.ctx = canvas.getContext("2d", { alpha: true });

    this.packets = [];
    this.packetCursor = 0;

    this.palette = Array.from({ length: 16 }, () => [0, 0, 0, 255]);
    this.pixels = new Uint8Array(this.width * this.height); // palette indexes
    this.imageData = this.ctx.createImageData(this.width, this.height);
  }

  async load(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load CDG: ${res.status}`);
    const buffer = await res.arrayBuffer();
    const bytes = new Uint8Array(buffer);

    this.packets = [];
    for (let offset = 0; offset + 24 <= bytes.length; offset += 24) {
      this.packets.push(bytes.subarray(offset, offset + 24));
    }

    this.reset();
  }

  reset() {
    this.packetCursor = 0;
    this.pixels.fill(0);
    this.draw();
  }

  renderAt(timeSeconds) {
    const targetPacket = Math.max(0, Math.floor(timeSeconds * 300));

    if (targetPacket < this.packetCursor) {
      this.reset(); // seek backward
    }

    while (this.packetCursor <= targetPacket && this.packetCursor < this.packets.length) {
      this.applyPacket(this.packets[this.packetCursor]);
      this.packetCursor += 1;
    }

    this.draw();
  }

  applyPacket(packet) {
    const command = packet[0] & 0x3f;
    const instruction = packet[1] & 0x3f;
    const data = packet.subarray(4, 20);

    if (command !== 0x09) return;

    switch (instruction) {
      case 1:
        this.memoryPreset(data);
        break;
      case 2:
        this.borderPreset(data);
        break;
      case 6:
        this.tileBlock(data, false);
        break;
      case 38:
        this.tileBlock(data, true);
        break;
      case 30:
        this.loadColorTable(data, 0);
        break;
      case 31:
        this.loadColorTable(data, 8);
        break;
      // Scroll commands can be added after basic rendering works.
    }
  }

  memoryPreset(data) {
    const color = data[0] & 0x0f;
    this.pixels.fill(color);
  }

  borderPreset(data) {
    const color = data[0] & 0x0f;

    for (let y = 0; y < this.height; y++) {
      for (let x = 0; x < this.width; x++) {
        const inBorder = x < 6 || x >= 294 || y < 12 || y >= 204;
        if (inBorder) {
          this.pixels[y * this.width + x] = color;
        }
      }
    }
  }

  loadColorTable(data, offset) {
    for (let i = 0; i < 8; i++) {
      const b1 = data[i * 2] & 0x3f;
      const b2 = data[i * 2 + 1] & 0x3f;

      const r = ((b1 & 0x3c) >> 2) * 17;
      const g = (((b1 & 0x03) << 2) | ((b2 & 0x30) >> 4)) * 17;
      const b = (b2 & 0x0f) * 17;

      this.palette[offset + i] = [r, g, b, 255];
    }
  }

  tileBlock(data, xorMode) {
    const color0 = data[0] & 0x0f;
    const color1 = data[1] & 0x0f;
    const row = data[2] & 0x1f;
    const col = data[3] & 0x3f;

    const x0 = col * 6;
    const y0 = row * 12;

    for (let y = 0; y < 12; y++) {
      const byte = data[4 + y] & 0x3f;

      for (let x = 0; x < 6; x++) {
        const bit = (byte >> (5 - x)) & 1;
        const color = bit ? color1 : color0;
        const px = x0 + x;
        const py = y0 + y;

        if (px >= 0 && px < this.width && py >= 0 && py < this.height) {
          const index = py * this.width + px;
          this.pixels[index] = xorMode ? (this.pixels[index] ^ color) : color;
        }
      }
    }
  }

  draw() {
    const out = this.imageData.data;

    for (let i = 0; i < this.pixels.length; i++) {
      const [r, g, b, a] = this.palette[this.pixels[i]];
      const j = i * 4;
      out[j] = r;
      out[j + 1] = g;
      out[j + 2] = b;
      out[j + 3] = a;
    }

    this.ctx.putImageData(this.imageData, 0, 0);
  }
}

const audio = document.querySelector("#primary-audio");
const canvas = document.querySelector("#cdg-canvas");

const cdg = new CdgRenderer(canvas);

await cdg.load("media.cdg");

function tick() {
  cdg.renderAt(audio.currentTime || 0);

  if (!audio.paused && !audio.ended) {
    requestAnimationFrame(tick);
  }
}

audio.addEventListener("play", tick);
audio.addEventListener("seeked", () => {
  cdg.renderAt(audio.currentTime || 0);
});