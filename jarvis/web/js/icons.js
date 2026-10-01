// Line icons (24x24, stroke = currentColor).
const P = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9v12h14V9"/><path d="M10 21v-6h4v6"/>',
  editor: '<path d="M3 5h6l2 2h10v12H3z"/><path d="m10 11.5-2 2 2 2"/><path d="m14 11.5 2 2-2 2"/>',
  settings: '<path d="M4 6h9"/><path d="M17 6h3"/><path d="M4 12h3"/><path d="M11 12h9"/><path d="M4 18h11"/><path d="M19 18h1"/><rect x="13" y="4" width="4" height="4"/><rect x="7" y="10" width="4" height="4"/><rect x="15" y="16" width="4" height="4"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/><path d="M9 21h6"/>',
  micOff: '<path d="M15 9.5V6a3 3 0 0 0-5.7-1.3"/><path d="M9 9v2a3 3 0 0 0 5 2.2"/><path d="M5 11a7 7 0 0 0 11.5 5.4"/><path d="M19 11a7 7 0 0 1-.6 2.8"/><path d="M12 18v3"/><path d="M9 21h6"/><path d="m3 3 18 18"/>',
  send: '<path d="M4 12h15"/><path d="m13 6 6 6-6 6"/>',
  trash: '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v6"/><path d="M14 11v6"/>',
  plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
  folder: '<path d="M3 5h6l2 2h10v12H3z"/>',
  folderOpen: '<path d="M3 19V5h6l2 2h8v3"/><path d="M3 19 6 10h16l-3 9z"/>',
  folderPlus: '<path d="M3 5h6l2 2h10v12H3z"/><path d="M12 10v6"/><path d="M9 13h6"/>',
  file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
  filePlus: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M12 11v6"/><path d="M9 14h6"/>',
  command: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="m9 12 2 2-2 2"/><path d="M13 17h2"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  more: '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  copy: '<rect x="8" y="8" width="12" height="12"/><path d="M16 8V4H4v12h4"/>',
  play: '<path d="M7 4v16l13-8z"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7"/>',
  x: '<path d="M6 6l12 12"/><path d="M18 6 6 18"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.7-4.3"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.7 4.3"/><path d="M20 20v-4h-4"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/>',
  moon: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z"/>',
  volume: '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16.5 9a4 4 0 0 1 0 6"/><path d="M19 6.5a7.5 7.5 0 0 1 0 11"/>',
  volumeOff: '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="m17 10 4 4"/><path d="m21 10-4 4"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff: '<path d="M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.1"/><path d="M6.6 6.6C3.7 8.5 2 12 2 12s3.5 7 10 7a9.8 9.8 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/><path d="m3 3 18 18"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9"/><path d="m17 6 3 3"/><path d="m14 9 2 2"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="m6.5 6.5 2 2M15.5 15.5l2 2M6.5 17.5l2-2M15.5 8.5l2-2"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c3 3.2 3 14.8 0 18"/><path d="M12 3c-3 3.2-3 14.8 0 18"/>',
  keyboard: '<rect x="2" y="6" width="20" height="12"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M6 14h.01M18 14h.01M9 14h6"/>',
  arrowUp: '<path d="M12 19V5"/><path d="m6 11 6-6 6 6"/>',
  arrowDown: '<path d="M12 5v14"/><path d="m6 13 6 6 6-6"/>',
  external: '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 14v6H4V6h6"/>',
  repeat: '<path d="M17 2l3 3-3 3"/><path d="M4 11V9a4 4 0 0 1 4-4h12"/><path d="M7 22l-3-3 3-3"/><path d="M20 13v2a4 4 0 0 1-4 4H4"/>',
  stop: '<rect x="6" y="6" width="12" height="12"/>',
  grid: '<rect x="4" y="4" width="6" height="6"/><rect x="14" y="4" width="6" height="6"/><rect x="4" y="14" width="6" height="6"/><rect x="14" y="14" width="6" height="6"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h1M4 12h1M4 18h1"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  unlink: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/><path d="m3 3 18 18"/>',
  data: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><path d="M12 7.5v.01"/>',
  bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  window: '<rect x="3" y="4" width="18" height="16"/><path d="M3 9h18"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  power: '<path d="M12 3v8"/><path d="M6.3 6.3a8 8 0 1 0 11.4 0"/>',
  cursor: '<path d="M5 3l14 7-6 2-2 6z"/>',
  message: '<path d="M4 4h16v12H8l-4 4z"/>',
  music: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
  terminal: '<rect x="3" y="4" width="18" height="16"/><path d="m7 9 3 3-3 3"/><path d="M12 15h5"/>',
  wait: '<path d="M7 3h10"/><path d="M7 21h10"/><path d="M8 3c0 5 8 6 8 9s-8 4-8 9"/><path d="M16 3c0 5-8 6-8 9"/>',
  grip: '<circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/>',
};

export function icon(name, size = 18, cls = '') {
  const body = P[name] || P.info;
  return `<svg class="ico ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="square" stroke-linejoin="miter" aria-hidden="true">${body}</svg>`;
}

// The Jarvis logo: exact geometry of the original artwork. Each block can be animated.
export function logo(cls = '') {
  return `<svg class="logo-svg ${cls}" viewBox="97 255 885 569" fill="currentColor" role="img" aria-label="Jarvis">
    <rect class="lg lg-dot lg-dot-a" x="97" y="255" width="114" height="88"/>
    <rect class="lg lg-blk lg-tl" x="281" y="414" width="113" height="167"/>
    <rect class="lg lg-blk lg-tr" x="493" y="414" width="111" height="167"/>
    <rect class="lg lg-blk lg-c" x="387" y="572" width="112" height="89"/>
    <rect class="lg lg-blk lg-bl" x="281" y="657" width="113" height="167"/>
    <rect class="lg lg-blk lg-br" x="493" y="657" width="111" height="167"/>
    <rect class="lg lg-dot lg-dot-b" x="869" y="735" width="113" height="89"/>
  </svg>`;
}
