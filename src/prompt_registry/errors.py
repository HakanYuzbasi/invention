"""Typed error hierarchy. All domain errors derive from RegistryError so the
CLI can map them to a clean non-zero exit without leaking tracebacks."""


class RegistryError(Exception):
    """Base class for all expected, user-facing errors."""


class ValidationError(RegistryError):
    """Invalid input: bad slug, malformed variable spec, bad check params."""


class NotFoundError(RegistryError):
    """A prompt, version, case, or run does not exist."""


class AlreadyExistsError(RegistryError):
    """Attempt to create an entity whose identifier is already taken."""


class RenderError(RegistryError):
    """Template rendering failed: missing/unknown variables or bad template."""


class StorageError(RegistryError):
    """The registry database is missing, incompatible, or unreadable."""
