import plistlib

import pytest

from developer_disk_image.exceptions import GithubRateLimitExceededError
from developer_disk_image.repo import DeveloperDiskImageRepository


@pytest.mark.xfail(raises=GithubRateLimitExceededError)
def test_developer_disk_image():
    repo = DeveloperDiskImageRepository.create()
    assert repo.get_developer_disk_image('16.4') is not None
    assert repo.get_developer_disk_image('16.4aaaa') is None


@pytest.mark.xfail(raises=GithubRateLimitExceededError)
def test_personalized_disk_image():
    repo = DeveloperDiskImageRepository.create()
    assert repo.get_personalized_disk_image() is not None


@pytest.mark.xfail(raises=GithubRateLimitExceededError)
def test_cryptex_disk_image():
    # NOTE: reads the `main` tree, so this only passes once the assets are merged.
    repo = DeveloperDiskImageRepository.create()
    cryptex_disk_image = repo.get_cryptex_disk_image()
    info = plistlib.loads(cryptex_disk_image.cryptex_info)
    assert info['CFBundleIdentifier'] == 'com.apple.MobileAsset.DDI'
    assert info['RequiredMountPath'] == '/System/Developer'
    assert cryptex_disk_image.image and cryptex_disk_image.trustcache and cryptex_disk_image.root_hash
