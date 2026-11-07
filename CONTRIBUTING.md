# Contributing

**English** · [Italiano](CONTRIBUTING.it.md)

If you want to help, reports, ideas and pull requests are welcome.

- For problems and ideas, open an [issue](https://github.com/erpaffo/Pozzo-Launcher/issues/new/choose) and pick the right template.
- **Security**: never in public, see [SECURITY.md](SECURITY.md).
- If you have a question about how to use the app, check the [manual](https://erpaffo.github.io/Pozzo-Launcher/) first (in Italian).

## Setting up

You need Python 3.12 (the same as CI and releases).

```bash
python -m pip install -r requirements.txt
python -m pozzo app        # runs the app from source
```

The sources use the same data folder as the installed executable. To avoid touching your library while developing, use a separate configuration: `POZZO_CONFIG=/path/to/test/config.toml`.

## Tests

```bash
PYTHONUTF8=1 python packaging/run_tests.py          # the whole suite, like CI
PYTHONUTF8=1 python tests/test_pipeline.py          # a single file
```

Tests are plain scripts with `assert`, there is no framework to learn. CI runs them on Windows, macOS and Linux on every push and pull request. For JavaScript, `node --check <file>.js` is enough.

## Style

- Code follows the style of the neighboring files: names, comments (in Italian, short, about the *why*) and structure.
- A small, complete change beats a big one: also update tests, the manual (`docs/`) and any callers you touch.
- No new dependencies for a few lines.

## Changelog and versions

Changelog entries are added with the script, not by hand:

```bash
python tools/version.py add aggiunto "What changes for people using the app"   # aggiunto, cambiato, migliorato, corretto, rimosso
python tools/version.py status
```

The version number, the version commit and releases are handled by the maintainer.

## Extensions

Extensions live in `extensions/<id>/` and are installed from the store inside the app. Guide: [Themes and plugins](https://erpaffo.github.io/Pozzo-Launcher/ESTENSIONI/). After changing one:

```bash
python tools/extensions.py index    # regenerates extensions/index.json (a test checks it)
python tools/extensions.py install  # copies it into your plugins folder to try it (redo after every change)
```

## License of contributions

By submitting a pull request you agree that your contribution is distributed under the same license as the project (see `LICENSE`).
