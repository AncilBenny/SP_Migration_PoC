"""Opt-in Microsoft Entra delegated Graph authentication using MSAL.

Browser/PKCE public-client flow. No token/cache persistence to reports or CIR.
Actual file permission is enforced by Graph/SharePoint, not local readiness.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from uuid import UUID
import re

AUTHORITY_HOST = 'https://login.microsoftonline.com'
DEFAULT_SCOPE = 'Files.Read'
DELEGATED_READ_SCOPES = frozenset({
    'Files.Read', 'Sites.Selected', 'Files.SelectedOperations.Selected',
})

class EntraAuthError(ValueError):
    """Stable redacted code; never include MSAL responses or exceptions."""
    def __init__(self, code: str):
        if not re.fullmatch(r'ENTRA_[A-Z_]{1,50}', code):
            code = 'ENTRA_AUTH_FAILED'
        super().__init__(code)

def _guid(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F-]{36}', value):
        raise EntraAuthError('ENTRA_INVALID_IDENTIFIER')
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise EntraAuthError('ENTRA_INVALID_IDENTIFIER') from None
    if parsed.int == 0 or str(parsed) != value.lower():
        raise EntraAuthError('ENTRA_INVALID_IDENTIFIER')
    return str(parsed)

@dataclass(frozen=True)
class DelegatedAuthConfig:
    tenant_id: str
    client_id: str
    scope: str = DEFAULT_SCOPE
    allow_interactive: bool = True
    login_hint: str | None = None

    def __post_init__(self):
        object.__setattr__(self, 'tenant_id', _guid(self.tenant_id))
        object.__setattr__(self, 'client_id', _guid(self.client_id))
        if self.scope not in DELEGATED_READ_SCOPES:
            raise EntraAuthError('ENTRA_SCOPE_NOT_ALLOWED')
        if type(self.allow_interactive) is not bool:
            raise EntraAuthError('ENTRA_INVALID_MODE')
        if self.login_hint is not None and (not isinstance(self.login_hint, str)
           or len(self.login_hint) > 254 or not re.fullmatch(r'[^\s\x00-\x1f<>]{3,254}', self.login_hint)):
            raise EntraAuthError('ENTRA_INVALID_LOGIN_HINT')

    @property
    def authority(self) -> str:
        return f'{AUTHORITY_HOST}/{self.tenant_id}'

    def readiness(self) -> dict[str, Any]:
        """Offline configuration presence, not proof of consent or access."""
        return {
            'authMode': 'entra-delegated-system-browser-pkce',
            'tenantConfigured': True, 'clientConfigured': True,
            'scopeRequested': self.scope,
            'interactiveAllowed': self.allow_interactive,
            'tokenCache': 'process-memory-only',
            'selectedResourceGrant': 'not-verified',
            'graphAuthorization': 'not-verified',
            'permissionApproved': False,
        }

class EntraDelegatedTokenProvider:
    """Callable GraphBinaryFetcher token supplier; MSAL is lazily imported."""
    def __init__(self, config: DelegatedAuthConfig, *, msal_module=None):
        if not isinstance(config, DelegatedAuthConfig):
            raise EntraAuthError('ENTRA_INVALID_CONFIG')
        self.config = config
        if msal_module is None:
            try:
                import msal as msal_module
            except ImportError:
                raise EntraAuthError('ENTRA_MSAL_NOT_INSTALLED') from None
        try:
            self._app = msal_module.PublicClientApplication(
                config.client_id, authority=config.authority,
                token_cache=msal_module.SerializableTokenCache(),
            )
        except Exception:
            raise EntraAuthError('ENTRA_CLIENT_INIT_FAILED') from None

    def __call__(self) -> str:
        cfg = self.config
        scopes = [cfg.scope]
        try:
            accounts = self._app.get_accounts(username=cfg.login_hint) if cfg.login_hint else self._app.get_accounts()
        except Exception:
            raise EntraAuthError('ENTRA_ACCOUNT_LOOKUP_FAILED') from None
        if not isinstance(accounts, list):
            raise EntraAuthError('ENTRA_ACCOUNT_LOOKUP_FAILED')
        if len(accounts) > 1:
            raise EntraAuthError('ENTRA_MULTIPLE_ACCOUNTS')
        if accounts:
            try:
                silent = self._app.acquire_token_silent_with_error(scopes, account=accounts[0])
            except Exception:
                raise EntraAuthError('ENTRA_SILENT_ACQUISITION_FAILED') from None
            if silent and isinstance(silent, dict) and silent.get('access_token'):
                return self._token(silent)
            if silent and isinstance(silent, dict) and silent.get('error') and not cfg.allow_interactive:
                raise EntraAuthError('ENTRA_REAUTH_REQUIRED')
        if not cfg.allow_interactive:
            raise EntraAuthError('ENTRA_INTERACTIVE_REQUIRED')
        try:
            result = self._app.acquire_token_interactive(scopes=scopes, login_hint=cfg.login_hint)
        except Exception:
            raise EntraAuthError('ENTRA_INTERACTIVE_FAILED') from None
        return self._token(result)

    def _token(self, result: Any) -> str:
        if not isinstance(result, dict) or not result.get('access_token'):
            raise EntraAuthError('ENTRA_TOKEN_ACQUISITION_FAILED')
        token = result['access_token']
        if not isinstance(token, str) or not (1 <= len(token) <= 16384) or any(c.isspace() for c in token):
            raise EntraAuthError('ENTRA_INVALID_TOKEN')
        granted = result.get('scope')
        if granted is not None:
            if not isinstance(granted, str) or self.config.scope.lower() not in {s.lower() for s in granted.split()}:
                raise EntraAuthError('ENTRA_SCOPE_NOT_GRANTED')
        return token
