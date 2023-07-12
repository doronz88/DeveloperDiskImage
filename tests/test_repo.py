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
