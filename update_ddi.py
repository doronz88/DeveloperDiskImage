# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Refresh this repository's DDI payloads from a local Xcode installation.

macOS only -- it reads Xcode's own DDI bundle out of ``/Library/Developer``. The published result
is plain files, so every other OS can consume them through :mod:`developer_disk_image.repo`.

    uv run --script update_ddi.py                 # refresh every variant of the iOS DDI
    uv run --script update_ddi.py --dry-run       # report what would change, write nothing
    uv run --script update_ddi.py --platform tvOS --variant cryptex

``--script`` keeps uv from treating the surrounding repository as a project, which would leave a
stray ``uv.lock`` and ``.venv`` behind. This script needs no third-party packages either way.

Two variants are published per platform:

``Xcode_<platform>_DDI_Personalized``
    What the image mounter needs: the ``PersonalizedDMG`` and its loadable trust cache, published
    under fixed names (``Image.dmg`` / ``Image.dmg.trustcache``) because released pymobiledevice3
    versions fetch exactly those paths.

``Xcode_<platform>_DDI_Cryptex``
    What ``cryptexd`` needs: the four ``Cryptex1,*`` assets. These keep the relative paths their
    ``BuildManifest.plist`` declares -- which embed a build number and therefore change between
    releases -- so that a downloaded copy is a drop-in ``Restore`` directory. Consumers resolve
    the names by reading the manifest, exactly as the daemon's own tooling does.
"""

import argparse
import hashlib
import plistlib
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple

DEFAULT_SOURCE_ROOT = Path('/Library/Developer')
PERSONALIZED_IMAGES = 'PersonalizedImages'
PLATFORMS = ('iOS', 'tvOS', 'watchOS', 'xrOS')


@dataclass(frozen=True)
class Variant:
    """One publishable flavour of a DDI bundle.

    :param name: suffix of the published directory, e.g. ``Personalized``.
    :param marker: manifest key that identifies the build identity describing this variant.
    :param payloads: manifest key -> published file name.
    """

    name: str
    marker: str
    payloads: Mapping[str, str]


PERSONALIZED = Variant(
    name='Personalized',
    marker='PersonalizedDMG',
    payloads={'PersonalizedDMG': 'Image.dmg', 'LoadableTrustCache': 'Image.dmg.trustcache'},
)
CRYPTEX = Variant(
    name='Cryptex',
    marker='Cryptex1,GenericDmg',
    payloads={
        'Cryptex1,GenericDmg': 'Image.dmg',
        'Cryptex1,GenericTrustCache': 'Image.dmg.trustcache',
        'Cryptex1,CryptexInfoPlist': 'Image.dmg.cryptex_info',
        'Cryptex1,GenericVolume': 'Image.dmg.root_hash',
    },
)
VARIANTS = {'personalized': PERSONALIZED, 'cryptex': CRYPTEX}


@dataclass
class Payload:
    """A single file about to be published."""

    key: str
    source: Path
    relative_path: str
    data: bytes
    digest_agreements: int
    digest_total: int


@contextmanager
def attached(dmg: Path) -> Iterator[Path]:
    """Attach a disk image read-only for the duration of the block, then detach it."""
    output = subprocess.run(
        ['hdiutil', 'attach', '-nobrowse', '-readonly', '-plist', str(dmg)],
        check=True, capture_output=True).stdout
    mount_points = [
        Path(entity['mount-point'])
        for entity in plistlib.loads(output)['system-entities'] if entity.get('mount-point')]
    if not mount_points:
        raise SystemExit(f'{dmg} attached without a mount point')
    try:
        yield mount_points[0]
    finally:
        subprocess.run(['hdiutil', 'detach', str(mount_points[0])], check=False, capture_output=True)


@contextmanager
def restore_directory(source_root: Path, platform: str) -> Iterator[Path]:
    """Locate the platform's unpacked ``Restore`` directory, attaching the candidate DMG if needed.

    Xcode keeps an already-expanded copy under ``DeveloperDiskImages``; when that is absent (a
    fresh Xcode that has not yet been asked for this platform) the pristine image still sits in
    ``CoreDevice/CandidateDDIs`` and is attached instead.
    """
    expanded = source_root / 'DeveloperDiskImages' / f'{platform}_DDI' / 'Restore'
    if (expanded / 'BuildManifest.plist').is_file():
        yield expanded
        return

    candidate = source_root / 'CoreDevice' / 'CandidateDDIs' / f'{platform}_DDI.dmg'
    if not candidate.is_file():
        raise SystemExit(
            f'no {platform} DDI under {source_root}: neither {expanded} nor {candidate} exists.\n'
            'Install Xcode, or open it once so it expands its DDI bundles.')
    with attached(candidate) as mount_point:
        restore = mount_point / 'Restore'
        if not (restore / 'BuildManifest.plist').is_file():
            raise SystemExit(f'{candidate} has no Restore/BuildManifest.plist')
        yield restore


def identities_with(build_manifest: Mapping[str, Any], marker: str) -> List[Mapping[str, Any]]:
    """Return every build identity whose manifest carries `marker`."""
    return [identity for identity in build_manifest['BuildIdentities'] if marker in identity['Manifest']]


def collect(restore: Path, build_manifest: Mapping[str, Any], variant: Variant) -> List[Payload]:
    """Read and verify every payload of `variant`.

    Each file is checked against the SHA-384 digests the manifest declares for it. Identities
    disagree in practice -- a bundle ships one file per path while some device classes declare a
    digest for content that is not shipped -- so a file is accepted when it matches any declared
    digest, and the agreement count is reported.

    :raises SystemExit: if a payload is missing or matches no declared digest.
    """
    identities = identities_with(build_manifest, variant.marker)
    if not identities:
        raise SystemExit(f'no build identity carries {variant.marker!r}; is this a {variant.name} bundle?')

    payloads = []
    for key, published_name in variant.payloads.items():
        entries = [identity['Manifest'][key] for identity in identities if key in identity['Manifest']]
        if not entries:
            raise SystemExit(f'{variant.name}: no build identity declares {key!r}')

        source = restore / entries[0]['Info']['Path']
        if not source.is_file():
            raise SystemExit(f'{variant.name}: {key} points at {source}, which does not exist')

        data = source.read_bytes()
        digest = hashlib.sha384(data).digest()
        digests = [entry.get('Digest') for entry in entries]
        agreements = digests.count(digest)
        if not agreements:
            raise SystemExit(
                f'{variant.name}: {source} does not match any of the {len(set(digests))} digests '
                f'{key!r} declares -- the bundle looks inconsistent, refusing to publish it')

        payloads.append(Payload(
            key=key,
            source=source,
            relative_path=published_name,
            data=data,
            digest_agreements=agreements,
            digest_total=len(entries),
        ))
    return payloads


def republish_manifest(build_manifest: Any, payloads: List[Payload], build_manifest_bytes: bytes) -> bytes:
    """Re-serialize the build manifest with every republished payload pointing at its new name.

    Payloads are published under fixed names so their download URLs stay predictable across
    releases, while Apple's own paths embed a build number. Left alone, the manifest would then
    describe files that are not there -- and consumers that resolve payloads through it (the way
    pymobiledevice3 loads Cryptex1 assets) would break. Only ``Info.Path`` is touched; the digests
    that personalization actually relies on are untouched.
    """
    published = {payload.key: payload.relative_path for payload in payloads}
    for identity in build_manifest['BuildIdentities']:
        for key, relative_path in published.items():
            entry = identity['Manifest'].get(key)
            if entry is not None:
                entry['Info']['Path'] = relative_path
    fmt = plistlib.FMT_BINARY if build_manifest_bytes.startswith(b'bplist') else plistlib.FMT_XML
    return plistlib.dumps(build_manifest, fmt=fmt)


def published_build_version(directory: Path) -> Optional[str]:
    """``ProductBuildVersion`` of the copy already published in `directory`, if any."""
    manifest = directory / 'BuildManifest.plist'
    if not manifest.is_file():
        return None
    try:
        return plistlib.loads(manifest.read_bytes()).get('ProductBuildVersion')
    except plistlib.InvalidFileException:
        return None


def human(size: int) -> str:
    """Render a byte count the way a maintainer wants to read it."""
    return f'{size / 1048576:.1f} MiB' if size >= 1048576 else f'{size:,}B'


def publish(directory: Path, files: Mapping[str, bytes], dry_run: bool) -> Tuple[int, int]:
    """Write `files` into `directory`, dropping anything else that is there.

    The directory is fully generated, so stale payloads from an older build -- whose names embed
    the previous build number -- must not survive.

    :returns: number of files written and number removed.
    """
    written = removed = 0

    stale = sorted(
        path for path in directory.rglob('*')
        if path.is_file() and str(path.relative_to(directory)) not in files)
    for path in stale:
        print(f'    - {path.relative_to(directory)} (stale)')
        if not dry_run:
            path.unlink()
        removed += 1

    for relative_path, data in files.items():
        destination = directory / relative_path
        if destination.is_file() and destination.read_bytes() == data:
            print(f'      {relative_path} unchanged ({human(len(data))})')
            continue
        state = 'updated' if destination.is_file() else 'new'
        print(f'    + {relative_path} {state} ({human(len(data))})')
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        written += 1

    if not dry_run:
        for path in sorted(directory.rglob('*'), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    return written, removed


def update(repo: Path, restore: Path, platform: str, variant: Variant, dry_run: bool) -> Tuple[int, int]:
    """Refresh one variant of one platform, reporting what changed."""
    build_manifest_bytes = (restore / 'BuildManifest.plist').read_bytes()
    build_manifest = plistlib.loads(build_manifest_bytes)
    build_version = build_manifest.get('ProductBuildVersion')

    directory = repo / PERSONALIZED_IMAGES / f'Xcode_{platform}_DDI_{variant.name}'
    previous = published_build_version(directory)
    transition = f'{previous} -> {build_version}' if previous != build_version else f'{build_version} (unchanged)'
    print(f'\n  {directory.relative_to(repo)}: {transition}')

    payloads = collect(restore, build_manifest, variant)
    for payload in payloads:
        agreement = f'{payload.digest_agreements}/{payload.digest_total} identities'
        print(f'      {payload.key}: {payload.source.name} -> {payload.relative_path} (sha384 ok, {agreement})')

    files: Dict[str, bytes] = {'BuildManifest.plist': republish_manifest(build_manifest, payloads, build_manifest_bytes)}
    files.update({payload.relative_path: payload.data for payload in payloads})
    directory.mkdir(parents=True, exist_ok=True)
    return publish(directory, files, dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source-root', type=Path, default=DEFAULT_SOURCE_ROOT,
                        help=f'where Xcode keeps its DDIs (default: {DEFAULT_SOURCE_ROOT})')
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parent,
                        help='repository root to update (default: this script\'s directory)')
    parser.add_argument('--platform', default='iOS', choices=PLATFORMS, help='DDI platform (default: iOS)')
    parser.add_argument('--variant', default='all', choices=('all',) + tuple(VARIANTS),
                        help='which variant to publish (default: all)')
    parser.add_argument('--dry-run', action='store_true', help='report what would change, write nothing')
    args = parser.parse_args()

    if sys.platform != 'darwin':
        parser.error('this script reads a local Xcode installation, so it only runs on macOS')

    selected = list(VARIANTS.values()) if args.variant == 'all' else [VARIANTS[args.variant]]

    written = removed = 0
    with restore_directory(args.source_root, args.platform) as restore:
        print(f'Reading {args.platform} DDI from {restore}')
        for variant in selected:
            variant_written, variant_removed = update(args.repo, restore, args.platform, variant, args.dry_run)
            written += variant_written
            removed += variant_removed

    print(f'\n{"Would write" if args.dry_run else "Wrote"} {written} file(s), '
          f'{"would remove" if args.dry_run else "removed"} {removed}.')
    if written or removed:
        print('Remember to bump LATEST_DDI_BUILD_ID in pymobiledevice3 to match.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
