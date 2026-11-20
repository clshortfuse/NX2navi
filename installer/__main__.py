"""Compatibility entrypoint for the retired installer."""
from installer import main

if __name__ == '__main__':
    raise SystemExit(main())
