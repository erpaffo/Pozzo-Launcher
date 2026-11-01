/* Set di icone del Pozzo: SVG inline, griglia 24x24, linea 1.5px, giunzioni arrotondate, currentColor.
 * - GS.icon(name, {size, cls, fill}) / ic(name, opts) -> stringa SVG (per i template JS);
 * - data-icon="nome" negli HTML statici;
 * - le emoji/simboli noti, a inizio testo di un elemento ("⚙ Impostazioni", "✕"), vengono sostituiti
 *   automaticamente nel DOM (anche per il contenuto creato dopo). Opt-out: data-noicon sull'elemento.
 */
(() => {
  "use strict";
  const ICONS = {
    well: '<path d="M5 6.2L12 2.8l7 3.4M7 6.6v4M17 6.6v4M12 6v4.4"/><path d="M4.5 12c0-1.3 3.4-2.3 7.5-2.3s7.5 1 7.5 2.3-3.4 2.3-7.5 2.3-7.5-1-7.5-2.3z"/><path d="M4.5 12v6.5c0 1.3 3.4 2.3 7.5 2.3s7.5-1 7.5-2.3V12"/><path d="M12 15v2.4M8 17.2v2.2M16 17.2v2.2"/>',
    home: '<path d="M3.5 11 12 4l8.5 7"/><path d="M5.5 9.7V19a1 1 0 001 1h11a1 1 0 001-1V9.7"/><path d="M12 12.6c-1 1.2-1.6 1.9-1.6 2.7a1.6 1.6 0 003.2 0c0-.8-.6-1.5-1.6-2.7z"/>',
    drop: '<path d="M12 3.5c3.2 4 5.5 6.8 5.5 10a5.5 5.5 0 01-11 0c0-3.2 2.3-6 5.5-10z"/>',
    bucket: '<path d="M5 8.5h14l-1.5 9.8a1.6 1.6 0 01-1.6 1.2H8.1a1.6 1.6 0 01-1.6-1.2z"/><path d="M7 8.5c0-3 2.2-4.8 5-4.8s5 1.8 5 4.8M6.2 13h11.6"/>',
    sparkle: '<path d="M11 3.5c.7 4 2.5 5.8 6.5 6.5-4 .7-5.8 2.5-6.5 6.5-.7-4-2.5-5.8-6.5-6.5 4-.7 5.8-2.5 6.5-6.5z"/><path d="M18.5 15.5v4.5M16.25 17.75h4.5"/>',
    grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    star: '<path d="M12 3.8l2.4 5 5.4.7-3.9 3.8.95 5.4L12 16.1l-4.85 2.6.95-5.4-3.9-3.8 5.4-.7z"/>',
    "star-fill": '<path class="f" d="M12 3.8l2.4 5 5.4.7-3.9 3.8.95 5.4L12 16.1l-4.85 2.6.95-5.4-3.9-3.8 5.4-.7z"/>',
    heart: '<path d="M12 19.5c-4.2-2.6-7-5.5-7-9a3.8 3.8 0 017-2 3.8 3.8 0 017 2c0 3.5-2.8 6.4-7 9z"/>',
    bag: '<path d="M5.2 8.5h13.6l-.9 10.2a1.5 1.5 0 01-1.5 1.3H7.6a1.5 1.5 0 01-1.5-1.3z"/><path d="M9 8.5V7.4a3 3 0 016 0v1.1"/>',
    users: '<circle cx="9" cy="8.5" r="3"/><path d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5"/><path d="M15.5 5.7a3 3 0 010 5.6M17.5 14.3c2 .5 3 2.3 3 4.7"/>',
    user: '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6"/>',
    gift: '<rect x="4" y="9" width="16" height="11" rx="1.5"/><path d="M3.5 9h17M12 9v11"/><path d="M12 9c-2.6 0-4-1-4-2.4s1-2.1 2.2-1.8C11.4 5.1 12 7 12 9zM12 9c2.6 0 4-1 4-2.4s-1-2.1-2.2-1.8C12.6 5.1 12 7 12 9z"/>',
    joystick: '<path d="M4.5 17.5c0-1 3.4-2 7.5-2s7.5 1 7.5 2v1c0 1.1-3.4 2-7.5 2s-7.5-.9-7.5-2z"/><path d="M12 15.5V8.5"/><circle cx="12" cy="6" r="2.6"/>',
    gamepad: '<path d="M7.5 7h9a4.5 4.5 0 014.4 3.6l.9 4.3a2.6 2.6 0 01-4.4 2.3L15.5 15.5h-7l-1.9 1.7a2.6 2.6 0 01-4.4-2.3l.9-4.3A4.5 4.5 0 017.5 7z"/><path d="M8 10v3M6.5 11.5h3M15.5 10.5h.01M17.5 12.5h.01"/>',
    camera: '<path d="M4 8.5A1.5 1.5 0 015.5 7h2L9.2 5h5.6L16.5 7h2A1.5 1.5 0 0120 8.5v9a1.5 1.5 0 01-1.5 1.5h-13A1.5 1.5 0 014 17.5z"/><circle cx="12" cy="13" r="3.3"/>',
    trophy: '<path d="M8 4.5h8v5a4 4 0 01-8 0z"/><path d="M8 6H5v1.5a3 3 0 003 3M16 6h3v1.5a3 3 0 01-3 3"/><path d="M12 13.5V17M9.5 19.5V17h5v2.5M8 19.5h8"/>',
    chart: '<rect x="4.5" y="11" width="3.5" height="8.5" rx=".8"/><rect x="10.25" y="5" width="3.5" height="14.5" rx=".8"/><rect x="16" y="13.5" width="3.5" height="6" rx=".8"/>',
    clock: '<circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/>',
    timer: '<circle cx="12" cy="13.5" r="6.5"/><path d="M12 10.5v3.2l2 1.2M9.5 3.5h5M12 3.5V7"/>',
    hourglass: '<path d="M7 4h10M7 20h10M8 4c0 4 3 5 4 8-1 3-4 4-4 8M16 4c0 4-3 5-4 8 1 3 4 4 4 8"/>',
    puzzle: '<path d="M4.5 8.5h3.2a2 2 0 114 0H15v3.2a2 2 0 110 4V19H4.5z"/>',
    gear: '<path d="M10.3 5.3L10.7 3.1h2.6l.4 2.2 1.9.8 1.8-1.3 1.8 1.8-1.3 1.8.8 1.9 2.2.4v2.6l-2.2.4-.8 1.9 1.3 1.8-1.8 1.8-1.8-1.3-1.9.8-.4 2.2h-2.6l-.4-2.2-1.9-.8-1.8 1.3-1.8-1.8 1.3-1.8-.8-1.9-2.2-.4v-2.6l2.2-.4.8-1.9-1.3-1.8 1.8-1.8 1.8 1.3z"/><circle cx="12" cy="12" r="2.8"/>',
    sliders: '<path d="M4.5 7h9M18.5 7h1M4.5 17h2M11.5 17h8"/><circle cx="16" cy="7" r="2.2"/><circle cx="9" cy="17" r="2.2"/>',
    keyboard: '<rect x="3" y="6.5" width="18" height="11" rx="2"/><path d="M7 10.5h.01M10 10.5h.01M13 10.5h.01M16 10.5h.01M7.5 14h9"/>',
    search: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "check-circle": '<circle cx="12" cy="12" r="8.5"/><path d="M8 12.3l2.8 2.8 5.4-5.6"/>',
    download: '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19.5h14"/>',
    upload: '<path d="M12 20V9M7.5 13.5L12 9l4.5 4.5M5 4.5h14"/>',
    refresh: '<path d="M19 12a7 7 0 11-2.1-5"/><path d="M17 3.5v3.7h-3.7"/>',
    stop: '<rect x="6.5" y="6.5" width="11" height="11" rx="1.8"/>',
    play: '<path d="M8 5.5v13l11-6.5z"/>',
    pause: '<path d="M9 6v12M15 6v12"/>',
    prev: '<path d="M6.5 5.5v13M18 6v12l-9.5-6z"/>',
    "playpause": '<path d="M4.5 6v12l8-6zM16 6v12M20 6v12"/>',
    trash: '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.8 12.2a1.3 1.3 0 001.3 1.3h6.8a1.3 1.3 0 001.3-1.3L17.5 7M10 11v5M14 11v5"/>',
    folder: '<path d="M3.5 7.5A1.5 1.5 0 015 6h4l2 2.2h8a1.5 1.5 0 011.5 1.5V17.5A1.5 1.5 0 0119 19H5a1.5 1.5 0 01-1.5-1.5z"/>',
    box: '<path d="M12 3.5l8 4v9l-8 4-8-4v-9z"/><path d="M4.3 7.7L12 11.5l7.7-3.8M12 11.5v9"/>',
    image: '<rect x="3.5" y="5" width="17" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M4 17l5-4.5 3.5 3L15 13.5l5 4.5"/>',
    bolt: '<path d="M13 3.5L5.5 13.5H11l-1 7 7.5-10H12z"/>',
    bulb: '<path d="M8.4 14.4a5.6 5.6 0 117.2 0c-.8.7-1.2 1.5-1.2 3.1H9.6c0-1.6-.4-2.4-1.2-3.1zM9.8 20h4.4"/>',
    dice: '<rect x="4.5" y="4.5" width="15" height="15" rx="3.5"/><path d="M9 9h.01M15 9h.01M12 12h.01M9 15h.01M15 15h.01"/>',
    clipboard: '<rect x="5.5" y="5" width="13" height="15.5" rx="2"/><path d="M9 5V4h6v1M9 10.5h6M9 14h6"/>',
    external: '<path d="M10 5.5H6.5A1.5 1.5 0 005 7v10.5A1.5 1.5 0 006.5 19H17a1.5 1.5 0 001.5-1.5V14M13.5 4.5h6v6M19.5 4.5L11 13"/>',
    "arrow-right": '<path d="M5 12h14M13.5 6.5L19 12l-5.5 5.5"/>',
    "arrow-left": '<path d="M19 12H5M10.5 6.5L5 12l5.5 5.5"/>',
    "arrow-up": '<path d="M12 19V5M6.5 10.5L12 5l5.5 5.5"/>',
    "arrow-down": '<path d="M12 5v14M6.5 13.5L12 19l5.5-5.5"/>',
    "chevron-left": '<path d="M14.5 6l-6 6 6 6"/>',
    "chevron-right": '<path d="M9.5 6l6 6-6 6"/>',
    "chevron-up": '<path d="M6 14.5l6-6 6 6"/>',
    "chevron-down": '<path d="M6 9.5l6 6 6-6"/>',
    warn: '<path d="M12 4.2L21 19.5H3z"/><path d="M12 10v4.3M12 17h.01"/>',
    edit: '<path d="M4.5 19.5l1-4.2L16.3 4.5a1.8 1.8 0 012.5 0l.7.7a1.8 1.8 0 010 2.5L8.7 18.5z"/><path d="M14.5 6.5l3 3"/>',
    globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.5 5.2 3.5 8.5s-1.1 6.1-3.5 8.5c-2.4-2.4-3.5-5.2-3.5-8.5S9.6 5.9 12 3.5z"/>',
    save: '<path d="M5.5 4.5h11l3 3V18a1.5 1.5 0 01-1.5 1.5H6A1.5 1.5 0 014.5 18V5.5a1 1 0 011-1z"/><path d="M8 4.5V9h7V4.5M8 19.5v-5h8v5"/>',
    key: '<circle cx="8" cy="15" r="3.5"/><path d="M10.5 12.5L19 4M16 7l2.5 2.5M13.5 9.5l2 2"/>',
    compass: '<circle cx="12" cy="12" r="8.5"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',
    library: '<rect x="4.5" y="4.5" width="4" height="15" rx="1"/><rect x="10" y="4.5" width="4" height="15" rx="1"/><path d="M15.8 6.8L19 6l3 12.2-3.2.8z"/>',
    fullscreen: '<path d="M4.5 9V5.5a1 1 0 011-1H9M15 4.5h3.5a1 1 0 011 1V9M19.5 15v3.5a1 1 0 01-1 1H15M9 19.5H5.5a1 1 0 01-1-1V15"/>',
    square: '<rect x="5" y="6" width="14" height="12" rx="1.8"/>',
    copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="1.5"/><path d="M15.5 8.5V6A1.5 1.5 0 0014 4.5H6A1.5 1.5 0 004.5 6v8A1.5 1.5 0 006 15.5h2.5"/>',
    menu: '<path d="M4.5 7h15M4.5 12h15M4.5 17h15"/>',
    mic: '<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0013 0M12 18v2.5"/>',
    volume: '<path d="M4.5 9.5h3L12 6v12l-4.5-3.5h-3z"/><path d="M15.5 9a4 4 0 010 6"/>',
    "volume-mute": '<path d="M4.5 9.5h3L12 6v12l-4.5-3.5h-3z"/><path d="M16 9.5l4 5M20 9.5l-4 5"/>',
    lock: '<rect x="5.5" y="10.5" width="13" height="9.5" rx="2"/><path d="M8.5 10.5V8a3.5 3.5 0 017 0v2.5"/>',
    rocket: '<path d="M12 3.5c3 2 4.5 5 4.5 8.5l-1.5 3h-6l-1.5-3c0-3.5 1.5-6.5 4.5-8.5z"/><circle cx="12" cy="10" r="1.6"/><path d="M7.5 13l-2 3.5 3-.5M16.5 13l2 3.5-3-.5M10.5 18.5L12 21l1.5-2.5"/>',
    mountain: '<path d="M3.5 19l6-10 3.5 5.5 2-3 5.5 7.5z"/>',
    diamond: '<path d="M7 5h10l3.5 5L12 20 3.5 10z"/><path d="M3.5 10h17M9 5l-1.5 5L12 20l4.5-10L15 5"/>',
    flame: '<path d="M12 3.5c.4 3-2.4 4.6-3.9 7a5.9 5.9 0 004 9c3.4.3 5.9-2.2 5.9-5.4 0-2-1-3.5-2.2-4.8-.2 1.2-.8 2-1.6 2.5.4-3-.9-6.5-2.2-8.3z"/>',
    moon: '<path d="M19 14.5A7.5 7.5 0 019.5 5a7.5 7.5 0 109.5 9.5z"/>',
    "thumb-down": '<path d="M8.5 14V5h-3a1 1 0 00-1 1v7a1 1 0 001 1zM8.5 14l3.2 5.5a1.7 1.7 0 003.1-1.2V15h3.7a1.5 1.5 0 001.5-1.7l-1.2-6.8A1.5 1.5 0 0018.3 5H8.5"/>',
    backspace: '<path d="M9 6h10.5a1 1 0 011 1v10a1 1 0 01-1 1H9l-5.5-6z"/><path d="M12.5 9.5l5 5M17.5 9.5l-5 5"/>',
    swap: '<path d="M4.5 8h13M14 4.5L17.5 8 14 11.5M19.5 16h-13M10 12.5L6.5 16 10 19.5"/>',
    phone: '<rect x="7" y="3.5" width="10" height="17" rx="2"/><path d="M11 17.5h2"/>',
    pointer: '<path d="M6 4l12 6.5-5.2 1.5-2.3 5.5z"/>',
    help: '<circle cx="12" cy="12" r="8.5"/><path d="M9.7 9.6a2.4 2.4 0 114 1.8c-.9.7-1.7 1.1-1.7 2.2M12 16.8h.01"/>',
    ban: '<circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/>'
  };

  // Glifo/emoji -> nome icona. Solo quelli usati come icone d'interfaccia.
  const MAP = {
    "◆": "well", "⌂": "home", "🏠": "home", "✨": "sparkle", "✦": "sparkle", "🆕": "sparkle", "🎉": "sparkle", "▦": "grid",
    "★": "star-fill", "⭐": "star-fill", "✪": "star-fill", "☆": "star", "♡": "heart", "❤": "heart", "🛒": "bag",
    "👥": "users", "👤": "user", "🎁": "gift", "🕹": "joystick", "🎮": "gamepad", "📷": "camera", "🏆": "trophy",
    "📊": "chart", "◷": "clock", "🕐": "clock", "⏱": "timer", "⏳": "hourglass", "🧩": "puzzle", "⚙": "gear",
    "🎛": "sliders", "⌨": "keyboard", "🔍": "search", "🔎": "search", "✕": "close", "✖": "close", "✓": "check",
    "✔": "check", "✅": "check-circle", "⬇": "download", "↓": "arrow-down", "⬆": "upload", "↑": "arrow-up",
    "↻": "refresh", "🔄": "refresh", "🔁": "refresh", "🌀": "refresh", "■": "stop", "⏹": "stop", "▶": "play",
    "⏯": "playpause", "⏮": "prev", "🗑": "trash", "📁": "folder", "📦": "box", "🖼": "image", "⚡": "bolt",
    "💡": "bulb", "🎲": "dice", "📋": "clipboard", "↗": "external", "→": "arrow-right", "←": "arrow-left",
    "◀": "chevron-left", "▲": "chevron-up", "▼": "chevron-down", "⚠": "warn", "✎": "edit", "✏": "edit",
    "🌐": "globe", "💾": "save", "🔑": "key", "🧭": "compass", "📚": "library", "⛶": "fullscreen", "▭": "square",
    "🗗": "copy", "⧉": "copy", "☰": "menu", "🎤": "mic", "🔉": "volume", "🔇": "volume-mute", "🔒": "lock",
    "🚀": "rocket", "🏔": "mountain", "💎": "diamond", "🔥": "flame", "🌙": "moon", "👎": "thumb-down",
    "⌫": "backspace", "⇄": "swap", "📱": "phone", "👆": "pointer", "🖱": "pointer", "❔": "help", "⊘": "ban"
  };

  const NS = 'xmlns="http://www.w3.org/2000/svg"';
  function icon(name, o) {
    o = o || {};
    const body = ICONS[name];
    if (!body) return "";
    const sz = o.size ? ` style="width:${typeof o.size === "number" ? o.size + "px" : o.size};height:${typeof o.size === "number" ? o.size + "px" : o.size}"` : "";
    const cls = "ic" + (o.cls ? " " + o.cls : "");
    return `<svg ${NS} class="${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false"${sz}>${body}</svg>`;
  }

  const css = document.createElement("style");
  css.textContent = ".ic{width:1em;height:1em;flex:none;vertical-align:-.15em;fill:none;stroke:currentColor;stroke-width:1.5;" +
    "stroke-linecap:round;stroke-linejoin:round}.ic .f{fill:currentColor}.nav-item .ico .ic,.snav-item .ico .ic{width:16px;height:16px}.logo .ic{width:1.15em;height:1.15em;vertical-align:-.2em}";
  document.head.appendChild(css);

  const glyphs = Object.keys(MAP).sort((a, b) => b.length - a.length).join("|");
  const LEAD = new RegExp("^(\\s*)(" + glyphs + ")\\uFE0F?(?=\\s|$)");
  const SHORT = new RegExp("(^|\\s)(" + glyphs + ")\uFE0F?(?=\\s|$)");
  const ANY = new RegExp(glyphs);
  const SKIP = "SCRIPT,STYLE,TEXTAREA,INPUT,OPTION,SELECT,TITLE,CODE,PRE,SVG,NOSCRIPT";
  const skipSet = new Set(SKIP.split(","));

  function build(name) {
    const t = document.createElement("template");
    t.innerHTML = icon(name);
    return t.content.firstChild;
  }

  function blocked(el) {
    for (; el && el.nodeType === 1; el = el.parentElement) {
      if (skipSet.has(el.tagName.toUpperCase()) || el.isContentEditable || el.hasAttribute("data-noicon")) return true;
    }
    return false;
  }

  function fixText(node) {
    const el = node.parentElement;
    if (blocked(el)) return;
    let first = true;
    for (;;) {
      const v = node.nodeValue;
      // testi brevi: ovunque; testi lunghi (descrizioni, note): solo a inizio riga
      const m = (v.length <= 90 ? SHORT : LEAD).exec(v);
      if (!m) return;
      const svg = build(MAP[m[2]]);
      const before = v.slice(0, m.index + m[1].length), rest = v.slice(m.index + m[0].length);
      const only = first && !before.trim() && !rest.trim() && !node.previousSibling && !node.nextSibling;
      first = false;
      if (before.trim()) node.parentNode.insertBefore(document.createTextNode(before), node);
      node.parentNode.insertBefore(svg, node);
      if (only && /^(BUTTON|A)$/.test(el.tagName) && !el.hasAttribute("aria-label") && el.title) el.setAttribute("aria-label", el.title);
      if (!rest) { node.remove(); return; }
      node.nodeValue = rest;
    }
  }
  function dataIcons(root) {
    const list = root.nodeType === 1 && root.hasAttribute("data-icon") ? [root] : [];
    if (root.querySelectorAll) list.push(...root.querySelectorAll("[data-icon]"));
    for (const el of list) {
      if (el.querySelector(":scope > svg.ic")) continue;
      const name = el.getAttribute("data-icon");
      if (!ICONS[name]) continue;
      const svg = build(name);
      el.textContent = "";
      el.appendChild(svg);
    }
  }

  function scan(root) {
    if (root.nodeType === 3) { if (ANY.test(root.nodeValue)) fixText(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) return;
    dataIcons(root);
    if (!ANY.test(root.textContent || "")) return;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: n => ANY.test(n.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT
    });
    const hits = [];
    for (let n = w.nextNode(); n; n = w.nextNode()) hits.push(n);
    hits.forEach(fixText);
  }

  let busy = false;
  const obs = new MutationObserver(muts => {
    if (busy) return;
    busy = true;
    try {
      for (const m of muts) {
        if (m.type === "characterData") scan(m.target);
        else m.addedNodes.forEach(scan);
      }
    } finally { busy = false; obs.takeRecords(); }
  });

  const GSo = window.GS || (window.GS = {});
  GSo.icon = icon;
  GSo.iconize = scan;
  GSo.ICONS = ICONS;
  window.ic = icon;

  scan(document.documentElement);
  obs.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
})();
