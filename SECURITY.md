# Security

**English** · [Italiano](SECURITY.it.md)

## Supported versions

Security fixes are released only for the **latest version** published in [Releases](https://github.com/erpaffo/Pozzo-Launcher/releases). The app notifies you on its own when a new one is available (Settings › About).

## How to report a vulnerability

**Do not open a public issue.** Use GitHub's private reporting:
[Security › Report a vulnerability](https://github.com/erpaffo/Pozzo-Launcher/security/advisories/new).

If you can, include: version and system, what the vulnerability allows, and the steps to reproduce it. You will get a reply as soon as possible; once the fix is published the report is made public, with your name if you wish.

## What matters most

Pozzo Launcher runs on your PC with your permissions. The exposed parts, and therefore the most important to report, are:

- **Phone server** (HTTPS on the home network): pairing with a code, access without pairing, what a paired phone or a guest can do.
- **App server** (`127.0.0.1` only): requests from other sites open in the browser (CSRF, DNS rebinding).
- **Extensions store**: an extension with a `backend.py` runs code. The store installs only files listed in the official index and with the correct sha256; a way around this check is a vulnerability.
- **Automatic update**: download and replacement of the executable.
- **Personal data**: source keys, store accounts and the library must not leave the PC (see [PRIVACY.md](PRIVACY.md)).

Third-party extensions installed by hand in the `plugins/` folder run with the same permissions as the app: their malicious behavior is not a vulnerability of Pozzo Launcher.
