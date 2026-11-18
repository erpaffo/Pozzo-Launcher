
// suoni generati con WebAudio: nessun file audio
const TONES = { soft: [[660, 0, .18], [880, .14, .28]], classic: [[523, 0, .12], [659, .12, .12], [784, .24, .12], [1047, .36, .4]] };
function beep(kind) {
  const seq = TONES[kind]; if (!seq) return;
  try {
    const a = new AudioContext(), g = a.createGain(); g.gain.value = .12; g.connect(a.destination);
    seq.forEach(([f, at, len]) => { const o = a.createOscillator(); o.type = kind === "soft" ? "sine" : "square"; o.frequency.value = f;
      o.connect(g); o.start(a.currentTime + at); o.stop(a.currentTime + at + len); });
  } catch (e) {}
}
window.showToast = (x) => {
  document.getElementById("k").textContent = (x.key && window.t ? t(x.key) : x.title) || "";
  document.getElementById("n").textContent = x.text || "";
  document.getElementById("d").textContent = x.desc || "";
  const i = document.getElementById("i"); i.hidden = !x.icon; if (x.icon) i.src = x.icon;
  const box = document.getElementById("t"); box.classList.remove("on"); void box.offsetWidth; box.classList.add("on");
  beep(x.sound);
};
