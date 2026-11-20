"""Copy a built v111 game into a portable folder for your own machines.

Only copies existing files; does not compile a second game executable. On Linux, system
libraries not already beside the executable must be installed on the destination machine.
By default the RomFS image is omitted: supply it separately or pass --with-romfs. Never share the output.
"""
import argparse
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mod_files import require_game_111

ROOT = Path(__file__).resolve().parent.parent
EXE = '.exe' if os.name == 'nt' else ''
STATE = ('romfs-index.bin', 'pipeline-cache.bin', 'pipeline-cache-play.bin', 'pipeline-keys.bin', 'shader-answers.bin',
         'shader-programs.bin', 'shader-prepared.bin', 'seed-answers.bin', 'seed-programs.bin')

def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src, dst, workers=16):
    jobs = []
    for dirpath, _, files in os.walk(src):
        rel = Path(dirpath).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        jobs += [(Path(dirpath) / f, dst / rel / f) for f in files if not f.endswith('.tmp')]
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(lambda j: shutil.copy2(*j), jobs))
    return len(jobs)


def size_of(path):
    return sum(f.stat().st_size for f in Path(path).rglob('*') if f.is_file())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--version', choices=('v111',), default='v111')
    ap.add_argument('--build', type=Path, default=ROOT / 'build' / 'v111', help='canonical game folder')
    ap.add_argument('--out', type=Path, default=ROOT / 'build' / 'v111-portable', help='empty destination folder')
    ap.add_argument('--with-romfs', action='store_true', help='also copy romfs/romfs.bin')
    ap.add_argument('--no-shader-cache', action='store_true', help='omit shader-cache')
    a = ap.parse_args()

    build, out = a.build.resolve(), a.out.resolve()
    if not any(out.is_relative_to((ROOT / name).resolve()) and out != (ROOT / name).resolve()
               for name in ('build', 'generated')):
        ap.error('--out must be under build or generated; this copy contains game data')
    if out == build or out.is_relative_to(build) or build.is_relative_to(out):
        ap.error('--out must not overlap the game folder')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        ap.error('--out must be empty')
    exe = build / f'ocarina{EXE}'
    xlate = build / f'nx2navi_xlate{EXE}'
    exefs = build / 'exefs'
    romfs = build / 'romfs' / 'romfs.bin'
    need = [exe, xlate, build / 'romfs-index.bin', *(exefs / n for n in ('main.npdm', 'sdk', 'subsdk0', 'rtld'))]
    if a.with_romfs:
        need.append(romfs)
    missing = [str(p) for p in need if not p.is_file()]
    if missing:
        ap.error('missing: ' + ', '.join(missing))
    try:
        require_game_111(exefs)
    except ValueError as error:
        ap.error(str(error))

    out.mkdir(parents=True, exist_ok=True)
    copy(exe, out / exe.name)
    for lib in build.iterdir():
        name = lib.name.lower()
        if lib.is_file() and (name.endswith('.dll') or '.so.' in name or name.endswith('.so')
                              or name == 'sl.interposer.json'):
            copy(lib, out / lib.name)
    copy(xlate, out / xlate.name)
    idf = xlate.with_suffix('.id')
    if idf.exists():
        copy(idf, out / 'nx2navi_xlate.id')
    for f in STATE:
        if (build / f).exists():
            copy(build / f, out / f)
        else:
            print(f'package_build: {f} not in {build}, skipped')
    n = copy_tree(exefs, out / 'exefs')
    for folder in sorted(build.iterdir()):
        if folder.is_dir() and (folder.name == 'shared-fonts' or folder.name == 'shaders'
                                or folder.name.startswith('romfs-patches')):
            n += copy_tree(folder, out / folder.name)
    if not a.no_shader_cache and (build / 'shader-cache').is_dir():
        n += copy_tree(build / 'shader-cache', out / 'shader-cache')
    (out / 'profile').mkdir(exist_ok=True)
    if a.with_romfs:
        (out / 'romfs').mkdir(exist_ok=True)
        print('package_build: copying romfs.bin ...')
        shutil.copyfile(romfs, out / 'romfs' / 'romfs.bin')
    print(f'package_build: {out}: {n} files in folders, {size_of(out) / 2**30:.2f} GiB'
          + ('' if a.with_romfs else f'; no RomFS: put romfs.bin into romfs{os.sep} or set NX2NAVI_ROMFS'))


if __name__ == '__main__':
    main()
