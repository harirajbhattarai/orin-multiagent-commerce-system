"""Stable control-plane failures mapped to safe HTTP responses."""


class ControlError(RuntimeError):
    """Base class for expected control-plane failures."""


class AuthenticationError(ControlError):
    """The bearer token is missing, invalid, expired, or not a user token."""


class ClientAccessDenied(ControlError):
    """The authenticated identity is not a member of the requested client."""


class InsufficientRole(ControlError):
    """The identity is a client member but cannot request execution."""


class RequestIntakeDisabled(ControlError):
    """The client is in maintenance or request intake is disabled."""


class RequestConflict(ControlError):
    """A request UUID was reused with different immutable inputs."""
