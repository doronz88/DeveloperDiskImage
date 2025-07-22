import base64
import dataclasses
import json
from datetime import datetime, timezone
from typing import Mapping, Optional

import requests

from developer_disk_image.exceptions import GithubRateLimitExceededError

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
    @classmethod
    def create(cls) -> 'DeveloperDiskImageRepository':
        return cls(cls._query(DEVELOPER_DISK_IMAGE_REPO_TREE_URL)['tree'])

    def __init__(self, tree: Mapping, github_token: Optional[str] = None):
        self._path_urls = {}
        for node in tree:
            self._path_urls[node['path']] = node
        self.github_token = github_token

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
        return base64.b64decode(self._query(url, github_token=self.github_token)['content'])

    @staticmethod
    def _query(url: str, github_token: Optional[str] = None) -> Mapping:
        headers = {}
        if github_token is not None:
            headers = {
                'Accept': 'application/vnd.github+json',
                'Authorization': 'Bearer ' + github_token,
                'X-GitHub-Api-Version': '2022-11-28'
            }
        response = requests.get(url, headers=headers)
        content = json.loads(response.text)
        if content.get('message', '').startswith('API rate limit exceeded'):
            reset_time = int(response.headers['X-RateLimit-Reset'])
            reset_utc = datetime.fromtimestamp(reset_time, timezone.utc)
            reset_local = reset_utc.astimezone()
            raise GithubRateLimitExceededError(
                f'GitHub API rate limit exceeded. Wait until {reset_local} or use a custom GitHub access token')
        return content
