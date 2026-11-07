// Telecomando del lettore: pubblica lo stato del player (window.__pmCtl, evento pm:state) al server e
// esegue i comandi che il telefono accoda (long-poll). Nessuna rete finche' non c'e' un lettore aperto.

export const STATE_EVERY_MS = 1000;
const KEYS = ["id", "paused", "episode", "season"];  // cambi che si inviano subito, senza aspettare il secondo

/** Pausa prima del prossimo poll dopo `fails` errori di fila: 0 se tutto va bene, poi 1 s raddoppiando fino a 30 s. */
export function nextPollDelay(fails) {
  return fails > 0 ? Math.min(30000, 1000 * 2 ** (fails - 1)) : 0;
}

/** Va inviato questo stato? Sempre se cambia play/pausa/episodio o l'attivita'; altrimenti al massimo 1 volta al secondo. */
export function shouldSendState(prev, next, lastSentAt, now) {
  if (!next) return false;
  if (!prev || !!prev.active !== !!next.active) return true;
  if (!next.active) return false;
  if (KEYS.some((k) => prev[k] !== next[k])) return true;
  return now - lastSentAt >= STATE_EVERY_MS;
}

let started = false;

export function startRemote(gs) {
  if (started || typeof window === "undefined") return;
  started = true;
  let prev = null, sentAt = 0, since = 0, polling = false, fails = 0;

  const send = (st) => {
    prev = st; sentAt = Date.now();
    gs.api("/api/media/remote/state", { method: "POST", body: st }).catch(() => {});
  };
  const onState = (e) => {
    const st = e.detail || { active: false };
    if (shouldSendState(prev, st, sentAt, Date.now())) send(st);
    if (st.active) poll(); // no-op se gia' in corso
  };
  async function poll() {
    if (polling || !window.__pmCtl) return;
    polling = true;
    while (window.__pmCtl) {
      try {
        const r = await gs.api(`/api/media/remote/poll?since=${since}`);
        fails = 0;
        since = r.last ?? since;
        for (const c of r.cmds || []) {
          since = Math.max(since, c.n);
          try { window.__pmCtl?.command(c.cmd, c.arg); } catch { /* un comando fallito non ferma il poll */ }
        }
      } catch {
        fails++;
        await new Promise((ok) => setTimeout(ok, nextPollDelay(fails)));
      }
    }
    polling = false;
  }
  window.addEventListener("pm:state", onState);
}
