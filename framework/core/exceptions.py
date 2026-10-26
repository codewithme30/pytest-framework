"""
Module  : framework.core.exceptions
Author  : Anil Kalisetti
Purpose : Small exception hierarchy so callers can catch framework errors precisely.
"""


class FrameworkError(Exception):
    """Base class for every error raised deliberately by the framework."""


class ConfigurationError(FrameworkError):
    """Configuration is missing, malformed or inconsistent (fix the config, not the test)."""


class IntegrationError(FrameworkError):
    """An external system (Jira, grid, database) rejected or failed a request."""
