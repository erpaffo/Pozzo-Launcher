/**
 * Pozzo Launcher - Download Manager & OS Detection
 * Rileva il sistema operativo dell'utente, interroga l'API di GitHub Releases
 * e aggiorna dinamicamente i link di download diretti e i metadati.
 */
(function () {
  'use strict';

  var REPO = 'erpaffo/Pozzo-Launcher';
  var API_URL = 'https://api.github.com/repos/' + REPO + '/releases/latest';
  var RELEASES_PAGE = 'https://github.com/' + REPO + '/releases/latest';

  // Rilevamento del sistema operativo dell'utente
  function detectOS() {
    var ua = navigator.userAgent || '';
    var platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '';
    var p = platform.toLowerCase();
    var u = ua.toLowerCase();

    if (p.indexOf('win') !== -1 || u.indexOf('windows') !== -1) {
      return {
        id: 'windows',
        name: 'Windows',
        desc: 'Windows 10 / 11 (64-bit)',
        primaryExt: 'setup.exe',
        primaryLabel: 'Scarica l\'Installer (.exe)',
        portableExt: 'zip',
        portableLabel: 'Versione Portatile (.zip)',
        icon: 'windows'
      };
    }
    if (p.indexOf('mac') !== -1 || u.indexOf('macintosh') !== -1 || u.indexOf('mac os x') !== -1) {
      return {
        id: 'macos',
        name: 'macOS',
        desc: 'macOS 12+ (Apple Silicon)',
        primaryExt: 'dmg',
        primaryLabel: 'Scarica Immagine Disco (.dmg)',
        portableExt: 'zip',
        portableLabel: 'Versione Portatile (.zip)',
        icon: 'apple'
      };
    }
    if (p.indexOf('linux') !== -1 || u.indexOf('linux') !== -1 || u.indexOf('x11') !== -1) {
      return {
        id: 'linux',
        name: 'Linux',
        desc: 'Ubuntu, Debian, Fedora, Arch (64-bit)',
        primaryExt: 'deb',
        primaryLabel: 'Scarica Pacchetto .deb',
        portableExt: 'tar.gz',
        portableLabel: 'Archivio Portatile (.tar.gz)',
        icon: 'linux'
      };
    }

    // Default generico: Windows
    return {
      id: 'windows',
      name: 'Windows',
      desc: 'Windows 10 / 11 (64-bit)',
      primaryExt: 'setup.exe',
      primaryLabel: 'Scarica per Windows',
      portableExt: 'zip',
      portableLabel: 'Versione Portatile (.zip)',
      icon: 'windows'
    };
  }

  // Parse degli asset di release GitHub
  function parseAssets(assets) {
    var out = {
      winSetup: null,
      winZip: null,
      macDmg: null,
      macZip: null,
      linuxDeb: null,
      linuxTar: null,
      checksums: null,
      pdf: null
    };

    if (!Array.isArray(assets)) return out;

    for (var i = 0; i < assets.length; i++) {
      var a = assets[i];
      var n = a.name.toLowerCase();
      var url = a.browser_download_url;

      if (n.indexOf('windows') !== -1 && n.indexOf('setup.exe') !== -1) out.winSetup = a;
      else if (n.indexOf('windows') !== -1 && n.indexOf('.zip') !== -1) out.winZip = a;
      else if (n.indexOf('macos') !== -1 && n.indexOf('.dmg') !== -1) out.macDmg = a;
      else if (n.indexOf('macos') !== -1 && n.indexOf('.zip') !== -1) out.macZip = a;
      else if (n.indexOf('.deb') !== -1) out.linuxDeb = a;
      else if (n.indexOf('linux') !== -1 && n.indexOf('.tar.gz') !== -1) out.linuxTar = a;
      else if (n.indexOf('sha256sums') !== -1) out.checksums = a;
      else if (n.indexOf('manuale.pdf') !== -1) out.pdf = a;
    }
    return out;
  }

  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return '';
    var mb = bytes / (1024 * 1024);
    return mb.toFixed(1) + ' MB';
  }

  function formatDate(isoStr) {
    if (!isoStr) return '';
    try {
      var d = new Date(isoStr);
      return d.toLocaleDateString('it-IT', { year: 'numeric', month: 'long', day: 'numeric' });
    } catch (e) {
      return '';
    }
  }

  // Aggiorna gli elementi della UI
  function applyReleaseData(release, os) {
    var tag = (release && release.tag_name) || 'v0.14.3';
    var assets = parseAssets(release ? release.assets : []);

    // Aggiorna tutti i tag versione presenti
    var tagEls = document.querySelectorAll('.gh-release-tag');
    tagEls.forEach(function (el) {
      el.textContent = tag;
    });

    var dateEls = document.querySelectorAll('.gh-release-date');
    if (release && release.published_at) {
      var dateStr = formatDate(release.published_at);
      dateEls.forEach(function (el) {
        el.textContent = dateStr;
      });
    }

    // Identifica l'asset primario e secondario in base all'OS
    var primaryAsset = null;
    var portableAsset = null;

    if (os.id === 'windows') {
      primaryAsset = assets.winSetup;
      portableAsset = assets.winZip;
    } else if (os.id === 'macos') {
      primaryAsset = assets.macDmg;
      portableAsset = assets.macZip;
    } else if (os.id === 'linux') {
      primaryAsset = assets.linuxDeb;
      portableAsset = assets.linuxTar;
    }

    // 1. Aggiorna l'Hero Button nella Home
    var heroBtn = document.getElementById('hero-download-btn');
    var heroBtnText = document.getElementById('hero-download-text');
    var heroBtnSub = document.getElementById('hero-download-sub');
    var heroPortable = document.getElementById('hero-portable-link');
    var heroBadge = document.getElementById('hero-os-detected');

    if (heroBtn) {
      var downloadUrl = primaryAsset ? primaryAsset.browser_download_url : RELEASES_PAGE;
      heroBtn.href = downloadUrl;
      if (heroBtnText) {
        heroBtnText.textContent = 'Scarica per ' + os.name;
      }
      if (heroBtnSub) {
        var sizeText = primaryAsset ? ' (' + formatBytes(primaryAsset.size) + ')' : '';
        heroBtnSub.textContent = os.primaryLabel.replace('Scarica ', '') + sizeText;
      }
    }

    if (heroPortable) {
      if (portableAsset) {
        heroPortable.href = portableAsset.browser_download_url;
        var pSize = portableAsset.size ? ' (' + formatBytes(portableAsset.size) + ')' : '';
        heroPortable.textContent = os.portableLabel + pSize;
      } else {
        heroPortable.href = RELEASES_PAGE;
        heroPortable.textContent = os.portableLabel;
      }
    }

    if (heroBadge) {
      heroBadge.textContent = 'Rilevato ' + os.desc;
    }

    // 2. Aggiorna i pulsanti dettagliati nella pagina Download
    function bindAssetLink(elId, sizeId, asset, fallbackName) {
      var el = document.getElementById(elId);
      var sizeEl = document.getElementById(sizeId);
      if (el) {
        el.href = asset ? asset.browser_download_url : (RELEASES_PAGE + '/download/' + fallbackName);
      }
      if (sizeEl && asset && asset.size) {
        sizeEl.textContent = formatBytes(asset.size);
      }
    }

    bindAssetLink('dl-win-setup', 'dl-win-setup-size', assets.winSetup, 'PozzoLauncher-windows-x64-setup.exe');
    bindAssetLink('dl-win-zip', 'dl-win-zip-size', assets.winZip, 'PozzoLauncher-windows-x64.zip');
    bindAssetLink('dl-mac-dmg', 'dl-mac-dmg-size', assets.macDmg, 'PozzoLauncher-macos-arm64.dmg');
    bindAssetLink('dl-mac-zip', 'dl-mac-zip-size', assets.macZip, 'PozzoLauncher-macos-arm64.zip');
    bindAssetLink('dl-linux-deb', 'dl-linux-deb-size', assets.linuxDeb, 'pozzo_amd64.deb');
    bindAssetLink('dl-linux-tar', 'dl-linux-tar-size', assets.linuxTar, 'PozzoLauncher-linux-x64.tar.gz');
    bindAssetLink('dl-checksums', 'dl-checksums-size', assets.checksums, 'SHA256SUMS.txt');
    bindAssetLink('dl-manual-pdf', 'dl-manual-pdf-size', assets.pdf, 'PozzoLauncher-manuale.pdf');

    // Metti in risalto la scheda del sistema operativo rilevato
    var osCard = document.getElementById('card-os-' + os.id);
    if (osCard) {
      osCard.classList.add('recommended-os-card');
      var recBadge = osCard.querySelector('.recommended-os-badge');
      if (recBadge) {
        recBadge.style.display = 'inline-flex';
      }
    }

    // Release notes nel box di download
    var notesBox = document.getElementById('release-notes-content');
    if (notesBox && release && release.body) {
      // Semplice sanitizzazione e formattazione markdown
      notesBox.textContent = release.body;
    }
  }

  // Inizializzazione all'avvio
  function init() {
    var os = detectOS();

    // Imposta subito i dati basati sull'OS rilevato per feedback istantaneo senza attendere la rete
    applyReleaseData(null, os);

    // Effettua la richiesta non bloccante a GitHub Releases
    fetch(API_URL)
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        applyReleaseData(data, os);
      })
      .catch(function () {
        // Fallback silenzioso: i link predefiniti a /releases/latest restano operativi
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

