"""Application-level invitation errors without HTTP transport details."""


class PublicBaseURLConfigurationError(Exception):
    """A public invitation link cannot be built from the configured origin."""
