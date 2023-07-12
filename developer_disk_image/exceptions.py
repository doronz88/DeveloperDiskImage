class DeveloperDiskImageException(Exception):
    pass


class GithubRateLimitExceededError(DeveloperDiskImageException):
    pass
