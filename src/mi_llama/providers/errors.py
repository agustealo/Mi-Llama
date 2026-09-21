class ProviderError(RuntimeError):
    """Base model-provider failure."""


class ProviderUnavailableError(ProviderError):
    """The configured provider cannot currently be reached."""


class ProviderProtocolError(ProviderError):
    """The provider returned an invalid or incomplete response."""
