import base64
import dataclasses
import json
from typing import Mapping, Optional

import requests

DEVELOPER_DISK_IMAGE_REPO_TREE_URL = \
    'https://api.github.com/repos/doronz88/DeveloperDiskImage/git/trees/main?recursive=true'


@dataclasses.dataclass
class DeveloperDiskImage:
    image: bytes
    signature: bytes


@dataclasses.dataclass
class PersonalizedImage:
    image: bytes
    build_manifest: bytes
    trustcache: bytes


class DeveloperDiskImageRepository:
    @staticmethod
    def create() -> 'DeveloperDiskImageRepository':
        return DeveloperDiskImageRepository(json.loads(requests.get(DEVELOPER_DISK_IMAGE_REPO_TREE_URL).text)['tree'])

    def __init__(self, tree: Mapping):
        self._path_urls = {}
        for node in tree:
            self._path_urls[node['path']] = node

    def get_developer_disk_image(self, version: str) -> Optional[DeveloperDiskImage]:
        image = self._get_blob(f'DeveloperDiskImages/{version}/DeveloperDiskImage.dmg')
        signature = self._get_blob(f'DeveloperDiskImages/{version}/DeveloperDiskImage.dmg.signature')

        if image is None:
            return None

        return DeveloperDiskImage(image=image, signature=signature)

    def get_personalized_disk_image(self) -> PersonalizedImage:
        image = self._get_blob('PersonalizedImages/Xcode_iOS_DDI_Personalized/Image.dmg')
        build_manifest = self._get_blob('PersonalizedImages/Xcode_iOS_DDI_Personalized/BuildManifest.plist')
        trustcache = self._get_blob(
            'PersonalizedImages/Xcode_iOS_DDI_Personalized/Image.dmg.trustcache')
        return PersonalizedImage(image=image, build_manifest=build_manifest, trustcache=trustcache)

    def _get_blob(self, path: str) -> Optional[bytes]:
        url = self._path_urls.get(path, {}).get('url')
        if url is None:
            return None
        return base64.b64decode(json.loads(requests.get(url).text)['content'])
