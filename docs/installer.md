# Installer compatibility

The legacy `python -m installer`, `python -m installer.cli`, and `python -m installer.gui` commands no longer
install games. Install and rebuild requests exit with guidance instead of processing old inputs. The old setup's
package arguments and install state are not supported by the Ocarina of Time build.

The legacy GUI, its four translation catalogs, and generic setup helpers remain in the checkout. Run
`python -m installer.gui --selftest` to preview the translated screens with sample data; it does not install or launch a game.

- **Windows setup:** Use `NX2navi-Setup-<version>.exe` and select your own Ocarina of Time Switch 2 **1.1.1** `.nup`
  dump. See the [launcher guide](launcher.md).
- **Command-line build:** Use `tools/make_game.py` from the [build kit](README-BuildKit.md). Provide that same `.nup`
  via `--nup`, or its extracted folders via `--exefs` and `--romfs`. Use `--check` to verify the input without building.

The Python helper `installer.ini` remains importable for compatibility; it does not install or identify the game.
