"""
Zerodha authentication enums.
"""

from enum import Enum


class ZerodhaAuthStatus(Enum):
    CREATED = "created"
    LOGIN_URL_READY = "login_url_ready"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    LOGGED_OUT = "logged_out"
    ERROR = "error"


class ZerodhaSessionEnvironment(Enum):
    PRODUCTION = "production"
