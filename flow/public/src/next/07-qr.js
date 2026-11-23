  /* ---------- QR codes (byte mode, error correction M, versions 1–6): the 分享卡片's way back to the site ---------- */
  // Written out here rather than loaded from elsewhere (the page loads nothing from other sites). tools/ui_test.py reads
  // the codes back with the browser's own BarcodeDetector where it has one. Up to 106 bytes: plenty for a link.
  const QR = (() => {
    const BLOCKS = [null, [10, 1, 16], [16, 1, 28], [26, 1, 44], [18, 2, 32], [24, 2, 43], [16, 4, 27]];  // [ECC per block, blocks, data per block]
    const ALIGN = [null, [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34]];
    const EXP = new Array(512), LOG = new Array(256);  // GF(256) with x^8 + x^4 + x^3 + x^2 + 1
    for (let i = 0, x = 1; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 256) x ^= 0x11d; }
    for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
    const mul = (a, b) => (a && b ? EXP[LOG[a] + LOG[b]] : 0);
    function ecc(data, n) {  // Reed–Solomon: the remainder of data·x^n divided by the generator of degree n
      let g = [1];
      for (let i = 0; i < n; i++) { const ng = new Array(g.length + 1).fill(0); g.forEach((v, j) => { ng[j] ^= v; ng[j + 1] ^= mul(v, EXP[i]); }); g = ng; }
      const r = data.concat(new Array(n).fill(0));
      for (let i = 0; i < data.length; i++) { const f = r[i]; if (f) g.forEach((v, j) => { r[i + j] ^= mul(v, f); }); }
      return r.slice(data.length);
    }
    function codewords(bytes, ver) {
      const [ecN, blocks, per] = BLOCKS[ver], cap = blocks * per, bits = [];
      const put = (v, n) => { for (let i = n - 1; i >= 0; i--) bits.push((v >> i) & 1); };
      put(4, 4); put(bytes.length, 8); bytes.forEach(b => put(b, 8));
      put(0, Math.min(4, cap * 8 - bits.length));
      while (bits.length % 8) bits.push(0);
      const data = [];
      for (let i = 0; i < bits.length; i += 8) data.push(bits.slice(i, i + 8).reduce((a, b) => a * 2 + b, 0));
      for (let p = 0; data.length < cap; p++) data.push(p % 2 ? 0x11 : 0xec);
      const ds = [], es = [];
      for (let b = 0; b < blocks; b++) { const d = data.slice(b * per, (b + 1) * per); ds.push(d); es.push(ecc(d, ecN)); }
      const out = [];
      for (let i = 0; i < per; i++) ds.forEach(d => out.push(d[i]));
      for (let i = 0; i < ecN; i++) es.forEach(e => out.push(e[i]));
      return out;
    }
    const MASKS = [(r, c) => (r + c) % 2 === 0, r => r % 2 === 0, (r, c) => c % 3 === 0, (r, c) => (r + c) % 3 === 0,
      (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0, (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
      (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0, (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0];
    function penalty(m) {  // the standard's four rules; a lower score scans more easily (any mask is valid)
      const n = m.length; let s = 0, dark = 0;
      const line = get => { let run = 1; for (let i = 1; i < n; i++) { if (get(i) === get(i - 1)) { run++; if (run === 5) s += 3; else if (run > 5) s++; } else run = 1; } };
      for (let i = 0; i < n; i++) { line(j => m[i][j]); line(j => m[j][i]); }
      for (let r = 0; r < n - 1; r++) for (let c = 0; c < n - 1; c++) { const v = m[r][c]; if (v === m[r][c + 1] && v === m[r + 1][c] && v === m[r + 1][c + 1]) s += 3; }
      const pat = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], rev = pat.slice().reverse();
      const at = (get, i, p) => p.every((b, k) => (get(i + k) ? 1 : 0) === b);
      for (let i = 0; i < n; i++) for (let j = 0; j + 11 <= n; j++) {
        const row = k => m[i][k], col = k => m[k][i];
        if (at(row, j, pat) || at(row, j, rev)) s += 40;
        if (at(col, j, pat) || at(col, j, rev)) s += 40;
      }
      m.forEach(r => r.forEach(v => { if (v) dark++; }));
      return s + 10 * Math.max(0, Math.ceil(Math.abs(dark * 20 - n * n * 10) / (n * n)) - 1);
    }
    function matrix(text) {
      const bytes = Array.from(new TextEncoder().encode(text));
      let ver = 1;
      while (ver <= 6 && bytes.length > BLOCKS[ver][1] * BLOCKS[ver][2] - 2) ver++;
      if (ver > 6) throw new Error('link too long for the QR code');
      const n = 17 + 4 * ver, M = [...Array(n)].map(() => new Array(n).fill(false)), fn = [...Array(n)].map(() => new Array(n).fill(false));
      const set = (r, c, v) => { M[r][c] = v; fn[r][c] = true; };
      for (const [r0, c0] of [[0, 0], [0, n - 7], [n - 7, 0]]) {  // finders, with their light separators
        for (let r = -1; r <= 7; r++) for (let c = -1; c <= 7; c++) {
          const rr = r0 + r, cc = c0 + c; if (rr < 0 || cc < 0 || rr >= n || cc >= n) continue;
          set(rr, cc, r >= 0 && r <= 6 && c >= 0 && c <= 6 && (r === 0 || r === 6 || c === 0 || c === 6 || (r >= 2 && r <= 4 && c >= 2 && c <= 4)));
        }
      }
      for (let i = 8; i < n - 8; i++) { set(6, i, i % 2 === 0); set(i, 6, i % 2 === 0); }  // timing
      const al = ALIGN[ver], last = al[al.length - 1];
      for (const r of al) for (const c of al) {
        if ((r === 6 && c === 6) || (r === 6 && c === last) || (r === last && c === 6)) continue;
        for (let dr = -2; dr <= 2; dr++) for (let dc = -2; dc <= 2; dc++) set(r + dr, c + dc, Math.max(Math.abs(dr), Math.abs(dc)) !== 1);
      }
      set(n - 8, 8, true);  // the dark module
      for (let i = 0; i < 9; i++) { if (!fn[8][i]) set(8, i, false); if (!fn[i][8]) set(i, 8, false); }  // format areas, filled later
      for (let i = 0; i < 8; i++) { if (!fn[8][n - 1 - i]) set(8, n - 1 - i, false); if (!fn[n - 1 - i][8]) set(n - 1 - i, 8, false); }
      const bits = []; codewords(bytes, ver).forEach(b => { for (let i = 7; i >= 0; i--) bits.push((b >> i) & 1); });
      let k = 0;
      for (let right = n - 1; right >= 1; right -= 2) {  // two columns at a time, up then down, from the bottom right
        if (right === 6) right = 5;
        for (let v = 0; v < n; v++) for (let j = 0; j < 2; j++) {
          const c = right - j, r = ((right + 1) & 2) === 0 ? n - 1 - v : v;
          if (!fn[r][c]) { M[r][c] = k < bits.length && bits[k] === 1; k++; }
        }
      }
      let best = null;
      for (let mask = 0; mask < 8; mask++) {
        const m = M.map((row, r) => row.map((v, c) => (fn[r][c] ? v : v !== MASKS[mask](r, c))));
        const data = mask;  // level M is 00
        let rem = data; for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >> 9) * 0x537);
        const f = ((data << 10) | rem) ^ 0x5412, bit = i => ((f >> i) & 1) === 1;
        for (let i = 0; i <= 5; i++) m[i][8] = bit(i);
        m[7][8] = bit(6); m[8][8] = bit(7); m[8][7] = bit(8);
        for (let i = 9; i < 15; i++) m[8][14 - i] = bit(i);
        for (let i = 0; i < 8; i++) m[8][n - 1 - i] = bit(i);
        for (let i = 8; i < 15; i++) m[n - 15 + i][8] = bit(i);
        m[n - 8][8] = true;
        const score = penalty(m);
        if (!best || score < best.score) best = { m, score };
      }
      return best.m;
    }
    // Drawn dark on light at x, y, size px across, with the quiet zone (4 modules) inside that size.
    function draw(g, text, x, y, size, dark = '#13261b', light = '#ffffff') {
      const m = matrix(text), cells = m.length + 8, u = size / cells;
      g.fillStyle = light; g.fillRect(x, y, size, size); g.fillStyle = dark;
      m.forEach((row, r) => row.forEach((v, c) => { if (v) g.fillRect(x + (c + 4) * u, y + (r + 4) * u, Math.ceil(u), Math.ceil(u)); }));
    }
    return { matrix, draw };
  })();
