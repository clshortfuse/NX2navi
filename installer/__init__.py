"""Compatibility package for the retired installer and its INI helper."""
import sys


def main():
    print(
        'The legacy NX2navi installer is retired. For Ocarina of Time (Switch 2, game version 1.1.1), '
        'use NX2navi-Setup on Windows or run tools\\make_game.py from the build kit. '
        'See docs/launcher.md and docs/README-BuildKit.md.',
        file=sys.stderr,
    )
    return 2
