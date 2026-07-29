"""External integrations for the SEO module.

Every service degrades gracefully: when its credentials are absent it raises
ServiceUnavailable rather than crashing the request, so the dashboard stays
usable while integrations are still being provisioned.
"""


class ServiceUnavailable(Exception):
    """Raised when an integration is not configured or is unreachable."""

    def __init__(self, service: str, message: str):
        self.service = service
        self.message = message
        super().__init__(f"{service}: {message}")
