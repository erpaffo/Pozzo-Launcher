"use strict";

const LANGUAGE_ALIASES = new Map([
  ["en", "en"], ["eng", "en"], ["it", "it"], ["ita", "it"],
  ["es", "es"], ["spa", "es"], ["fr", "fr"], ["fra", "fr"], ["fre", "fr"],
  ["de", "de"], ["deu", "de"], ["ger", "de"], ["pt", "pt"], ["por", "pt"],
  ["pt-br", "pt-BR"], ["ptbr", "pt-BR"], ["nl", "nl"], ["dut", "nl"], ["nld", "nl"],
  ["ru", "ru"], ["rus", "ru"], ["ja", "ja"], ["jpn", "ja"], ["ko", "ko"], ["kor", "ko"],
  ["zh", "zh"], ["zho", "zh"], ["chi", "zh"], ["pl", "pl"], ["pol", "pl"],
  ["sv", "sv"], ["swe", "sv"], ["no", "no"], ["nor", "no"], ["da", "da"], ["dan", "da"],
  ["fi", "fi"], ["fin", "fi"], ["el", "el"], ["gre", "el"], ["ell", "el"],
  ["tr", "tr"], ["tur", "tr"], ["cs", "cs"], ["cze", "cs"], ["ces", "cs"],
  ["hu", "hu"], ["hun", "hu"], ["ro", "ro"], ["rum", "ro"], ["ron", "ro"],
  ["th", "th"], ["tha", "th"], ["vi", "vi"], ["vie", "vi"], ["id", "id"], ["ind", "id"],
  ["ar", "ar"], ["ara", "ar"], ["he", "he"], ["heb", "he"], ["uk", "uk"], ["ukr", "uk"],
]);

const LANGUAGE_NAMES = {
  en: "Inglese", it: "Italiano", es: "Spagnolo", fr: "Francese", de: "Tedesco",
  pt: "Portoghese", "pt-BR": "Portoghese brasiliano", nl: "Olandese", ru: "Russo",
  ja: "Giapponese", ko: "Coreano", zh: "Cinese", pl: "Polacco", sv: "Svedese",
  no: "Norvegese", da: "Danese", fi: "Finlandese", el: "Greco", tr: "Turco",
  cs: "Ceco", hu: "Ungherese", ro: "Rumeno", th: "Thai", vi: "Vietnamita",
  id: "Indonesiano", ar: "Arabo", he: "Ebraico", uk: "Ucraino",
};

function languageCodes(title) {
  const found = [];
  const groups = String(title || "").matchAll(/[\[(]([^[\]()]{1,48})[\])]/g);
  for (const [, group] of groups) {
    const tokens = group.toLowerCase().replace(/_/g, "-").split(/[,\s/+|;]+/).filter(Boolean);
    if (!tokens.length || tokens.length > 8) continue;
    const codes = tokens.map((token) => LANGUAGE_ALIASES.get(token));
    if (codes.some((code) => !code)) continue;
    for (const code of codes) if (!found.includes(code)) found.push(code);
  }
  return found.length ? found : ["en"];
}

function languageLabel(code) {
  return LANGUAGE_NAMES[code] || code;
}

const GSLanguages = Object.freeze({
  codes: languageCodes,
  label: languageLabel,
  labels: (title) => languageCodes(title).map(languageLabel),
});

if (typeof module !== "undefined" && module.exports) module.exports = GSLanguages;
if (typeof window !== "undefined") window.GSLanguages = GSLanguages;
