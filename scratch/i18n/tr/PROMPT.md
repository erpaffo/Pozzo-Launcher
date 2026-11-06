# Istruzioni di traduzione (UI di Pozzo Launcher, un launcher di giochi/ROM)

Traduci i VALORI di un file JSON piatto dall'italiano alla lingua indicata. Le chiavi restano identiche.

Regole:
1. Output: un JSON valido UTF-8 con ESATTAMENTE le stesse chiavi del file sorgente, stesso ordine, solo valori stringa. Nessun commento, nessuna chiave in più o in meno.
2. Segnaposto come `{nome}`, `{n}`, `{p}` devono restare identici (stesso nome, stesso numero, non tradotti). L'ordine nella frase può cambiare per la grammatica.
3. Tag HTML (`<code>`, `<b>`, `<br>`, `<a ...>`, `&amp;` ecc.) restano identici (stessi tag, stessi attributi), si traduce solo il testo in mezzo.
4. NON tradurre: Pozzo, Pozzo Launcher, Big Picture, Steam, Epic, GOG, Xbox, Discord, Spotify, Sunshine, Moonlight, nomi di emulatori (RPCS3, Dolphin, PCSX2, Ryujinx, Eden...), nomi di console/marchi, ES-DE, Pegasus, Playnite, RetroAchievements, nomi di file/percorsi/comandi, estensioni di file, tasti (Ctrl, Cmd, Esc, F11...), emoji e simboli (▶ ⚡ ✕ › … ecc.), unità tecniche (GB, MB, ms, Hz, FPS).
5. Tono: interfaccia di un'app, chiaro e naturale per un madrelingua, stessa lunghezza approssimativa (le etichette dei pulsanti devono restare brevi). Usa la forma di cortesia/2ª persona più comune nelle app in quella lingua. Terminologia coerente: "libreria", "gioco", "copertina", "impostazioni", "scaricamento/download", "salvataggio", "estensione", "grafica" (= tema di layout dell'interfaccia), "tema" (colori).
6. Una stringa uguale in italiano e nella lingua di arrivo (es. "OK", "Download") va lasciata così.
7. Per ar: testo arabo standard moderno, i segnaposto e i tag restano nell'ordine che serve; non aggiungere caratteri di direzione.
8. Se una stringa è un frammento (es. finisce con ":" o inizia minuscola), traducila come frammento.
