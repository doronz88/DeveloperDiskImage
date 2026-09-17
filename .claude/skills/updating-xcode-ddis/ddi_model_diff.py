#!/usr/bin/env python3
"""Report which device models a new Xcode DDI adds or drops versus the published one.

    ddi_model_diff.py                                        # origin/main vs local Xcode
    ddi_model_diff.py --ref v0.3.0                           # any git ref as the baseline
    ddi_model_diff.py --new path/to/BuildManifest.plist      # explicit new manifest
    ddi_model_diff.py --repo path/to/DeveloperDiskImage      # when not run from the checkout

Exit status is always 0; read the output.
"""

import argparse
import plistlib
import subprocess
from pathlib import Path


def summarize(manifest_bytes: bytes):
    manifest = plistlib.loads(manifest_bytes)
    boards = {
        (identity['Info'].get('DeviceClass'), identity.get('ApChipID'), identity.get('ApBoardID'))
        for identity in manifest['BuildIdentities']}
    return manifest.get('ProductBuildVersion'), set(manifest.get('SupportedProductTypes') or []), boards


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', type=Path, default=Path.cwd(), help='DeveloperDiskImage checkout')
    parser.add_argument('--ref', default='origin/main', help='git ref holding the published baseline')
    parser.add_argument('--platform', default='iOS', choices=('iOS', 'tvOS', 'watchOS', 'xrOS'))
    parser.add_argument('--new', type=Path, help='new BuildManifest.plist (default: the local Xcode one)')
    args = parser.parse_args()

    published = f'PersonalizedImages/Xcode_{args.platform}_DDI_Personalized/BuildManifest.plist'
    shown = subprocess.run(['git', '-C', str(args.repo), 'show', f'{args.ref}:{published}'], capture_output=True)
    if shown.returncode:
        raise SystemExit(f'{args.ref} publishes no {published}: {shown.stderr.decode().strip()}')
    old = shown.stdout
    new_path = args.new or Path(f'/Library/Developer/DeveloperDiskImages/{args.platform}_DDI/Restore/BuildManifest.plist')
    if not new_path.is_file():
        raise SystemExit(f'{new_path} does not exist; open Xcode once so it expands its DDI bundles, or pass --new')

    old_build, old_types, old_boards = summarize(old)
    new_build, new_types, new_boards = summarize(new_path.read_bytes())

    print(f'{args.platform} DDI: {old_build} ({args.ref}) -> {new_build} ({new_path})')
    print(f'SupportedProductTypes: {len(old_types)} -> {len(new_types)}')
    print(f'  added:   {", ".join(sorted(new_types - old_types)) or "none"}')
    print(f'  removed: {", ".join(sorted(old_types - new_types)) or "none"}')
    print(f'Boards (DeviceClass, ApChipID, ApBoardID): {len(old_boards)} -> {len(new_boards)}')
    for label, boards in (('added', new_boards - old_boards), ('removed', old_boards - new_boards)):
        print(f'  {label}: {", ".join(f"{d} ({c}/{b})" for d, c, b in sorted(boards, key=str)) or "none"}')


if __name__ == '__main__':
    main()
