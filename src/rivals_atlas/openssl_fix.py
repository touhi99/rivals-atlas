"""macOS: let LadybugDB find OpenSSL without Homebrew.

The macOS wheel of LadybugDB links to Homebrew's OpenSSL by absolute path (`/opt/homebrew/opt/openssl@3/lib/...`).
On a Mac without Homebrew the import fails, and since the graph engine is imported before the dashboard starts,
the whole app would refuse to start. When the Rivals Atlas launcher supplies this machine's two OpenSSL
libraries (`RIVALS_ATLAS_OPENSSL_DIR`), rewrite the extension's load commands to `@loader_path` and sign the
result ad hoc, as Apple Silicon requires.

No compiler is involved: the load commands are patched in place, before the extension is ever loaded. This runs
only on macOS and is a no-op everywhere else.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

LIBRARIES = ("libssl.3.dylib", "libcrypto.3.dylib")

# LC_LOAD_DYLIB, LC_ID_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LAZY_LOAD_DYLIB
_DYLIB_COMMANDS = {0xC, 0xD, 0x80000018, 0x8000001F, 0x20}
_MH_MAGIC_64 = 0xFEEDFACF
_FAT_MAGIC = b"\xca\xfe\xba\xbe"
_FAT_MAGIC_64 = b"\xca\xfe\xba\xbf"


class FixError(RuntimeError):
    pass


def ensure() -> None:
    """Make LadybugDB loadable before the app imports it. Raises FixError with a readable explanation."""
    if sys.platform != "darwin":
        return
    prepare_error = None
    vendor = os.environ.get("RIVALS_ATLAS_OPENSSL_DIR")
    if vendor and Path(vendor).is_dir():
        try:
            _prepare(Path(vendor))
        except (FixError, OSError, subprocess.SubprocessError) as e:
            prepare_error = e
    ok, error = _import_ladybug()
    if not ok and _looks_like_openssl(error):
        detail = f" ({prepare_error})" if prepare_error else ""
        raise FixError("the graph engine needs OpenSSL 3, which this Mac does not have. "
                       "Use the Rivals Atlas launcher for macOS, or run: brew install openssl@3" + detail)


def _import_ladybug() -> tuple[bool, str]:
    try:
        import ladybug  # noqa: F401  (only the import matters here)
        return True, ""
    except Exception as e:  # noqa: BLE001  (the message tells the caller what to do)
        return False, str(e)


def _looks_like_openssl(error: str) -> bool:
    low = error.lower()
    return "openssl" in low or "libssl" in low or "libcrypto" in low or "library not loaded" in low


def _prepare(vendor: Path) -> None:
    extension = _extension()
    package = extension.parent
    targets = [extension]
    for name in LIBRARIES:
        source = vendor / name
        if not source.exists():
            raise FixError(f"{name} is missing from {vendor}")
        dest = package / name
        if not dest.exists():
            shutil.copy2(source, dest)
            os.chmod(dest, 0o644)        # the Homebrew copy is read-only, and patching needs to write
            _unquarantine(dest)         # the launcher's folder came out of a downloaded zip
        targets.append(dest)
    todo = [target for target in targets if _needs_patch(target)]
    if not todo:
        return
    for target in todo:
        if not _patch(target):
            raise FixError(f"could not rewrite the load commands of {target.name}")
    _sign(todo)


def _extension() -> Path:
    spec = importlib.util.find_spec("ladybug")
    if spec is None or not spec.origin:
        raise FixError("the ladybug package is not installed")
    found = sorted(Path(spec.origin).parent.glob("_lbug*.so"))
    if not found:
        raise FixError(f"no LadybugDB extension in {Path(spec.origin).parent}")
    return found[0]


def _needs_patch(path: Path) -> bool:
    data = path.read_bytes()
    for start, end in _slices(data):
        for name in _dylib_names(data, start, end):
            if os.path.basename(name) in LIBRARIES and not name.startswith("@loader_path/"):
                return True
    return False


def _patch(path: Path) -> bool:
    """Point every dependency named libssl/libcrypto at `@loader_path`. Returns False when nothing matched."""
    data = bytearray(path.read_bytes())
    changed = False
    for start, end in _slices(data):
        changed |= _patch_slice(data, start, end)
    if changed:
        os.chmod(path, path.stat().st_mode | stat.S_IWUSR)
        path.write_bytes(data)
    return changed


def _slices(data: bytes | bytearray) -> list[tuple[int, int]]:
    if data[:4] not in (_FAT_MAGIC, _FAT_MAGIC_64):
        return [(0, len(data))]
    wide = data[:4] == _FAT_MAGIC_64
    count = int.from_bytes(data[4:8], "big")
    entry = 32 if wide else 20
    out = []
    for i in range(count):
        at = 8 + i * entry
        if wide:
            offset = int.from_bytes(data[at + 8:at + 16], "big")
            size = int.from_bytes(data[at + 16:at + 24], "big")
        else:
            offset = int.from_bytes(data[at + 8:at + 12], "big")
            size = int.from_bytes(data[at + 12:at + 16], "big")
        out.append((offset, offset + size))
    return out


def _dylib_names(data: bytes, start: int, end: int) -> list[str]:
    """The dependency paths in one Mach-O slice."""
    if int.from_bytes(data[start:start + 4], "little") != _MH_MAGIC_64:
        return []
    count = int.from_bytes(data[start + 16:start + 20], "little")
    at = start + 32
    names = []
    for _ in range(count):
        if at + 8 > end:
            break
        command = int.from_bytes(data[at:at + 4], "little")
        size = int.from_bytes(data[at + 4:at + 8], "little")
        if size < 8 or at + size > end:
            break
        if command in _DYLIB_COMMANDS:
            name_at = at + int.from_bytes(data[at + 8:at + 12], "little")
            room = at + size - name_at
            if room > 0:
                names.append(bytes(data[name_at:name_at + room]).split(b"\0", 1)[0].decode("utf-8", "replace"))
        at += size
    return names


def _patch_slice(data: bytearray, start: int, end: int) -> bool:
    if int.from_bytes(data[start:start + 4], "little") != _MH_MAGIC_64:
        return False
    count = int.from_bytes(data[start + 16:start + 20], "little")
    at = start + 32
    changed = False
    for _ in range(count):
        if at + 8 > end:
            return changed
        command = int.from_bytes(data[at:at + 4], "little")
        size = int.from_bytes(data[at + 4:at + 8], "little")
        if size < 8 or at + size > end:
            return changed
        if command in _DYLIB_COMMANDS:
            name_at = at + int.from_bytes(data[at + 8:at + 12], "little")
            room = at + size - name_at
            if room > 0:
                current = bytes(data[name_at:name_at + room]).split(b"\0", 1)[0].decode("utf-8", "replace")
                wanted = f"@loader_path/{os.path.basename(current)}"
                encoded = wanted.encode()
                if os.path.basename(current) in LIBRARIES and len(encoded) + 1 <= room:
                    data[name_at:name_at + room] = encoded + b"\0" * (room - len(encoded))
                    changed = True
        at += size
    return changed


def _unquarantine(path: Path) -> None:
    """The macOS bundle arrives from a downloaded zip; dyld may refuse a quarantined library."""
    xattr = Path("/usr/bin/xattr")
    if xattr.exists():
        subprocess.run([str(xattr), "-d", "com.apple.quarantine", str(path)],
                       capture_output=True, check=False)


def _sign(paths: list[Path]) -> None:
    codesign = Path("/usr/bin/codesign")
    if not codesign.exists():
        raise FixError("codesign is missing")
    for path in paths:
        done = subprocess.run([str(codesign), "--force", "--sign", "-", str(path)],
                              capture_output=True, text=True, check=False)
        if done.returncode != 0:
            raise FixError(done.stderr.strip() or f"codesign failed for {path.name}")
