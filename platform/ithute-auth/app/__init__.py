"""Ithute Auth application package.

Presentation overrides are installed before ``app.main`` imports the routers so the
security-critical OAuth implementation can stay independent from its HTML theme.
"""

from .oauth_theme import apply_oauth_theme

apply_oauth_theme()
