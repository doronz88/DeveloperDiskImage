# Overview

Store both types of Apple's DeveloperDiskImage files:

- `DeveloperDiskImage.dmg` & `DeveloperDiskImage.dmg.signature`
    - Used for each iOS version < 17.0
- The new Personalized images, but splitted to:
    - APFS
    - `BuildManifest.plist`
    - Trustcache

The split of the new format is requires for OS* other then macOS then will have trouble mounting the original APFS image
inside: `~/Library/Developer/DeveloperDiskImages`.

# Python package

Additionally, this repo provides a python API for accessing this repository.
You can install it as follows:

```shell
python3 -m pip install developer_disk_image
```

## Example usage

```python
from developer_disk_image.repo import DeveloperDiskImageRepository

repo = DeveloperDiskImageRepository.create()

# will get both the APFS and the signature file
developer_disk_image = repo.get_developer_disk_image('16.4')

# will get all necessary files for mount
personalized_disk_image = repo.get_personalized_disk_image()
```
