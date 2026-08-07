import dataclasses
from datetime import datetime, timezone
from typing import Optional

import requests

from developer_disk_image.exceptions import DeveloperDiskImageException, GithubRateLimitExceededError

#: Payloads are served straight off raw.githubusercontent.com rather than through the REST API.
#: That host is not subject to the API's 60-requests-per-hour anonymous quota, so no token is
#: needed, and it saves downloading a recursive tree listing of a repository full of disk images
#: just to resolve a handful of known paths.
DEVELOPER_DISK_IMAGE_REPO_RAW_URL_FORMAT = \
    'https://raw.githubusercontent.com/doronz88/DeveloperDiskImage/{ref}/{path}'
DEFAULT_REF = 'main'


@dataclasses.dataclass
class DeveloperDiskImage:
    image: bytes
    signature: bytes


@dataclasses.dataclass
class PersonalizedImage:
    image: bytes
    build_manifest: bytes
    trustcache: bytes


@dataclasses.dataclass
class CryptexImage:
    """The Cryptex1 assets cryptexd needs in order to install a DeveloperDiskImage cryptex."""
    image: bytes
    build_manifest: bytes
    trustcache: bytes
    cryptex_info: bytes
    root_hash: bytes


CRYPTEX_IMAGE_ROOT = 'PersonalizedImages/Xcode_iOS_DDI_Cryptex'

#: Field of `CryptexImage` -> its published file name. Fixed, so the URLs stay predictable across
#: releases; the published BuildManifest.plist is rewritten to declare these same names.
CRYPTEX_IMAGE_PAYLOADS = {
    'image': 'Image.dmg',
    'trustcache': 'Image.dmg.trustcache',
    'cryptex_info': 'Image.dmg.cryptex_info',
    'root_hash': 'Image.dmg.root_hash',
}


class DeveloperDiskImageRepository:
    @classmethod
    def create(cls, github_token: Optional[str] = None, ref: str = DEFAULT_REF) -> 'DeveloperDiskImageRepository':
        """Create a repository client. Performs no request of its own.

        :param github_token: optional token, forwarded on every request.
        :param ref: branch, tag or commit to read. Defaults to `DEFAULT_REF`; pass a commit to read
            a revision that is not merged yet, which is how CI checks a pull request against the
            payloads that pull request adds.
        """
        return cls(github_token=github_token, ref=ref)

    def __init__(self, github_token: Optional[str] = None, ref: str = DEFAULT_REF):
        """
        :param github_token: optional token, forwarded on every request.
        :param ref: branch, tag or commit to read payloads from.
        """
        self.github_token = github_token
        self.ref = ref

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

    def get_cryptex_disk_image(self) -> CryptexImage:
        """Fetch the Cryptex1 DeveloperDiskImage assets, for installing the DDI over cryptexd.

        Writing these out under their published names reproduces a directory that cryptexd clients
        accept as-is, since the build manifest shipped alongside them declares those same names.
        """
        payloads = {'build_manifest': self._get_blob(f'{CRYPTEX_IMAGE_ROOT}/BuildManifest.plist')}
        for field, name in CRYPTEX_IMAGE_PAYLOADS.items():
            payloads[field] = self._get_blob(f'{CRYPTEX_IMAGE_ROOT}/{name}')

        missing = sorted(field for field, blob in payloads.items() if blob is None)
        if missing:
            raise DeveloperDiskImageException(f'not published under {CRYPTEX_IMAGE_ROOT}: {", ".join(missing)}')
        return CryptexImage(**payloads)

    def _get_blob(self, path: str) -> Optional[bytes]:
        """Fetch one payload, or ``None`` if this revision does not publish it."""
        url = DEVELOPER_DISK_IMAGE_REPO_RAW_URL_FORMAT.format(ref=self.ref, path=path)
        headers = {}
        if self.github_token is not None:
            headers['Authorization'] = 'Bearer ' + self.github_token

        response = requests.get(url, headers=headers)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            # raw.githubusercontent.com is not under the REST API's hourly quota, but it can still
            # throttle abusive traffic, and an authenticated request can still be limited.
            # https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
            remaining = response.headers.get('x-ratelimit-remaining')
            if response.status_code in (403, 429) and remaining is not None and int(remaining) == 0:
                reset_utc = datetime.fromtimestamp(int(response.headers['x-ratelimit-reset']), timezone.utc)
                raise GithubRateLimitExceededError(
                    f'GitHub: rate limit exceeded. Wait until {reset_utc.astimezone()} '
                    f'or use a custom GitHub access token')
            raise DeveloperDiskImageException(f'GitHub: request for {path} failed: {response.status_code}')
        return response.content
