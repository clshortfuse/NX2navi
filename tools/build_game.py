"""Shared compiler and header helpers for the canonical v111 builder."""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


WIN = os.name == 'nt'
ROOT = Path(__file__).resolve().parent.parent
UCRT = Path(r'C:\msys64\ucrt64\bin')


def on_path(name):
    """name on PATH, else a path that does not exist (the tool check below names it)."""
    found = shutil.which(name)
    return Path(found) if found else Path('/usr/bin') / name


CLANG = UCRT / 'clang.exe' if WIN else on_path('clang')

# Flags for generated code, plus -march for the FP/SIMD lowering.
# --cpu v2 replaces the level for CPUs without AVX2/FMA; runtime/fma.c then supplies the correctly rounded fma the
# lowering needs (runtime/simd.h).
GEN_FLAGS = ['-O1', '-fno-strict-aliasing', '-Wno-return-type', '-Wno-unused-label', '-fvisibility=hidden',
             '-march=x86-64-v3']
RT_FLAGS = ['-O2', '-g', '-Wall', '-fno-strict-aliasing', '-march=x86-64-v3']


def set_cpu(cpu):
    """Target x86-64-v3 (the default) or x86-64-v2. RT_CPU_LEVEL lets runtime/main.c's self-test check the same
    instruction set the build was compiled for."""
    march = f'-march=x86-64-{cpu}'
    GEN_FLAGS[GEN_FLAGS.index('-march=x86-64-v3')] = march
    RT_FLAGS[RT_FLAGS.index('-march=x86-64-v3')] = march
    RT_FLAGS.append(f'-DRT_CPU_LEVEL={3 if cpu == "v3" else 2}')


if WIN:
    RT_FLAGS.append('-D_WIN32_WINNT=0x0A00')
    VMA_INCLUDE = UCRT.parent / 'include' / 'vma'
else:
    VMA_INCLUDE = Path('/usr/include')
# Without a system vk_mem_alloc.h, the header the build pins (VMA 3.4.0) is fetched once
# into toolchain/vma: one MIT header (THIRD_PARTY_NOTICES.md), checked against its hash.
VMA_FETCH = ('https://raw.githubusercontent.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator/v3.4.0/include/vk_mem_alloc.h',
             '8487b7995ad3b263eb73bc5b9a77d71aa69b6bef5d58a715c02d2663afd81f1a')
VMA_LOCAL = ROOT / 'toolchain' / 'vma'


def vma_include():
    """The directory holding vk_mem_alloc.h: the system's, else toolchain/vma, fetched there on first use."""
    if (VMA_INCLUDE / 'vk_mem_alloc.h').is_file():
        return VMA_INCLUDE
    dst = VMA_LOCAL / 'vk_mem_alloc.h'
    if not dst.is_file():
        url, sha = VMA_FETCH
        print(f'build_game: no {VMA_INCLUDE / "vk_mem_alloc.h"}; fetching VMA 3.4.0 into {VMA_LOCAL}')
        try:
            data = urllib.request.urlopen(url, timeout=60).read()
        except OSError as e:
            sys.exit(f'build_game: fetching {url} failed ({e}); install VMA or put vk_mem_alloc.h in {VMA_LOCAL}')
        if hashlib.sha256(data).hexdigest() != sha:
            sys.exit(f'build_game: {url} does not match the pinned hash')
        VMA_LOCAL.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    return VMA_LOCAL


def system_vulkan_version(clang, env=None):
    """VK_HEADER_VERSION of the <vulkan/vulkan_core.h> this compiler finds by itself (its own search path, CPATH
    included), 0 when it finds none."""
    probe = '#include <vulkan/vulkan_core.h>\nnx2navi_vulkan_headers VK_HEADER_VERSION\n'
    try:
        p = subprocess.run([str(clang), '-E', '-P', '-x', 'c', '-'], input=probe, capture_output=True, text=True,
                           env=env, errors='replace')
    except OSError:
        return 0
    m = re.search(r'nx2navi_vulkan_headers\s+(\d+)', p.stdout) if p.returncode == 0 else None
    return int(m.group(1)) if m else 0


def vulkan_include(clang=None, env=None):
    """A build with the system's own headers (Linux without --deps): the folder to put ahead of them for
    <vulkan/vulkan.h>, or None when the system's serve. The runtime names Vulkan extensions newer than the headers
    many distributions package, and every file that does fails to compile there (tools/vulkan_pin.py). So:
    toolchain/vulkan-headers when it holds the pinned release (a kit carries it; a checkout once it was fetched), else
    nothing when the system's headers are at least that release, else the pinned release, fetched there once.
    Windows takes MSYS2's headers and returns None."""
    if WIN:
        return None
    import vulkan_pin
    local = ROOT / vulkan_pin.FOLDER
    if vulkan_pin.have(local):
        return local / 'include'
    found = system_vulkan_version(clang or CLANG, env)
    if found >= vulkan_pin.HEADER_VERSION:
        return None
    print(f'build_game: the system\'s Vulkan headers are {f"release {found}" if found else "missing"}; the runtime is '
          f'built against release {vulkan_pin.HEADER_VERSION} ({vulkan_pin.VERSION}) or newer', flush=True)
    return vulkan_pin.resolve(local) / 'include'


JOB_MEM = 768 << 20


if __name__ == '__main__':
    sys.exit('Use tools/make_game.py for v111 game builds and --make-runtime-lib for the runtime library.')
