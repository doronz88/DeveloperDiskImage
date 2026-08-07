import os
import plistlib

import pytest

from developer_disk_image.exceptions import GithubRateLimitExceededError
from developer_disk_image.repo import DEFAULT_REF, DeveloperDiskImageRepository


def repository() -> DeveloperDiskImageRepository:
    """Read the revision under test, so a pull request is checked against its own payloads.

    Reading `main` unconditionally would mean a pull request that publishes new files could never
    see them, and would only go green after being merged.
    """
    return DeveloperDiskImageRepository.create(
        github_token=os.getenv('GITHUB_TOKEN'), ref=os.getenv('GITHUB_SHA') or DEFAULT_REF)


@pytest.mark.xfail(raises=GithubRateLimitExceededError)
def test_developer_disk_image():
    repo = repository()
    assert repo.get_developer_disk_image('16.4') is not None
    assert repo.get_developer_disk_image('16.4aaaa') is None


@pytest.mark.xfail(raises=GithubRateLimitExceededError)
def test_personalized_disk_image():
    repo = repository()
    assert repo.get_personalized_disk_image() is not None


@pytest.mark.xfail(raises=GithubRateLimitExceededError)
def test_cryptex_disk_image():
    cryptex_disk_image = repository().get_cryptex_disk_image()
    info = plistlib.loads(cryptex_disk_image.cryptex_info)
    assert info['CFBundleIdentifier'] == 'com.apple.MobileAsset.DDI'
    assert info['RequiredMountPath'] == '/System/Developer'
    assert cryptex_disk_image.image and cryptex_disk_image.trustcache and cryptex_disk_image.root_hash


@pytest.mark.xfail(raises=GithubRateLimitExceededError)
def test_cryptex_build_manifest_declares_the_published_names():
    """The published manifest must describe the published layout, or a downloaded copy is unusable."""
    cryptex_disk_image = repository().get_cryptex_disk_image()
    identity = next(identity for identity in plistlib.loads(cryptex_disk_image.build_manifest)['BuildIdentities']
                    if 'Cryptex1,GenericDmg' in identity['Manifest'])
    assert identity['Manifest']['Cryptex1,GenericDmg']['Info']['Path'] == 'Image.dmg'
    assert identity['Manifest']['Cryptex1,CryptexInfoPlist']['Info']['Path'] == 'Image.dmg.cryptex_info'
