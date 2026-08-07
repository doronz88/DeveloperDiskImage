[![Pypi version](https://img.shields.io/pypi/v/developer_disk_image.svg)](https://pypi.org/project/developer_disk_image/ "PyPi package")

# Overview

Store both types of Apple's DeveloperDiskImage files:

- `DeveloperDiskImage.dmg` & `DeveloperDiskImage.dmg.signature`
    - Used for each iOS version < 17.0
- The new Personalized images, but splitted to:
    - APFS
    - `BuildManifest.plist`
    - Trustcache
- The Cryptex1 assets, for installing the same DDI through `cryptexd` instead of the image mounter:
    - APFS
    - `BuildManifest.plist`
    - Trustcache
    - Cryptex info plist
    - Volume root hash

The split of the new format is requires for OS* other than macOS that will have trouble extracting the original APFS
image inside: `~/Library/Developer/DeveloperDiskImages`.

## Layout

| Directory | Consumed by |
|---|---|
| `DeveloperDiskImages/<version>/` | iOS < 17.0 |
| `PersonalizedImages/Xcode_iOS_DDI_Personalized/` | the image mounter (`mounter auto-mount`) |
| `PersonalizedImages/Xcode_iOS_DDI_Cryptex/` | `cryptexd` (`cryptex auto-install`) |

Every payload is published under a fixed file name, so download URLs stay predictable across
releases:

| File | Personalized | Cryptex |
|---|---|---|
| `BuildManifest.plist` | yes | yes |
| `Image.dmg` | `PersonalizedDMG` | `Cryptex1,GenericDmg` |
| `Image.dmg.trustcache` | `LoadableTrustCache` | `Cryptex1,GenericTrustCache` |
| `Image.dmg.cryptex_info` | -- | `Cryptex1,CryptexInfoPlist` |
| `Image.dmg.root_hash` | -- | `Cryptex1,GenericVolume` |

Apple's own paths embed a build number (`022-22107-072.dmg`), so the published
`BuildManifest.plist` is rewritten to declare the fixed names instead. Only `Info.Path` is
adjusted -- the digests personalization depends on are untouched -- which keeps a downloaded
cryptex directory usable as a drop-in `Restore` directory.

## Updating

`update_ddi.py` refreshes every variant from a local Xcode installation. macOS only, no
dependencies, run it with [uv](https://docs.astral.sh/uv/):

```shell
uv run --script update_ddi.py             # refresh every variant of the iOS DDI
uv run --script update_ddi.py --dry-run   # report what would change, write nothing
uv run --script update_ddi.py --platform tvOS --variant cryptex
```

Pass `--script` so uv runs it as a standalone script rather than treating this repository as a uv
project (which would leave a stray `uv.lock` and `.venv` behind).

It reads Xcode's bundle from `/Library/Developer` (falling back to attaching
`CoreDevice/CandidateDDIs/<platform>_DDI.dmg` when no expanded copy exists), verifies every payload
against the SHA-384 digests in the build manifest before publishing it, and removes stale files
left over from a previous build. Remember to bump `LATEST_DDI_BUILD_ID` in pymobiledevice3 to match
whatever build it reports.

# Python package

Additionally, this repo provides a python API for accessing this repository.
You can install it as follows:

```shell
python3 -m pip install -U developer_disk_image
```

## Example usage

```python
from developer_disk_image.repo import DeveloperDiskImageRepository

repo = DeveloperDiskImageRepository.create()

# will get both the APFS and the signature file
developer_disk_image = repo.get_developer_disk_image('16.4')

# will get all necessary files for mount
personalized_disk_image = repo.get_personalized_disk_image()

# will get all necessary files for installing the DDI as a cryptex
cryptex_disk_image = repo.get_cryptex_disk_image()
```

Writing the cryptex assets back out under their published names produces a directory that
`cryptexd` clients accept as-is:

```python
from pathlib import Path

from developer_disk_image.repo import CRYPTEX_IMAGE_PAYLOADS

restore = Path('Xcode_iOS_DDI_Cryptex')
restore.mkdir(parents=True, exist_ok=True)
(restore / 'BuildManifest.plist').write_bytes(cryptex_disk_image.build_manifest)
for field, name in CRYPTEX_IMAGE_PAYLOADS.items():
    (restore / name).write_bytes(getattr(cryptex_disk_image, field))
```
