import dataclasses
import json
from datetime import datetime, timezone
from typing import Mapping, Optional, Union

import requests

from developer_disk_image.exceptions import GithubRateLimitExceededError, DeveloperDiskImageException

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
    def create(cls, github_token: Optional[str] = None) -> 'DeveloperDiskImageRepository':
        tree = cls._query(DEVELOPER_DISK_IMAGE_REPO_TREE_URL, github_token=github_token)['tree']
        return cls(tree, github_token=github_token)

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
        return self._query(url, raw=True, github_token=self.github_token)

    @staticmethod
    def _query(url: str, raw: bool = False, github_token: Optional[str] = None) -> Union[Mapping, bytes]:
        headers = {
            'X-GitHub-Api-Version': '2022-11-28',
            'Accept': 'application/vnd.github.raw+json' if raw else 'application/vnd.github+json'
        }
        if github_token is not None:
            headers['Authorization'] = 'Bearer ' + github_token
        response = requests.get(url, headers=headers)
        status_code = response.status_code
        if status_code != 200:
            # https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api?apiVersion=2022-11-28#exceeding-the-rate-limit
            if (status_code == 403 or status_code == 429) and int(response.headers['x-ratelimit-remaining']) == 0:
                reset_time = int(response.headers['x-ratelimit-reset'])
                reset_utc = datetime.fromtimestamp(reset_time, timezone.utc)
                reset_local = reset_utc.astimezone()
                raise GithubRateLimitExceededError(
                    f'GitHub API: rate limit exceeded. Wait until {reset_local} or use a custom GitHub access token')
            raise DeveloperDiskImageException(f'GitHub API: request failed: {response.status_code}')
        if raw:
            content = response.content
            if content is None:
                DeveloperDiskImageException('GitHub API: no content returned')
            return content
        return json.loads(response.text)
