"""Verify access tokens issued by an external auth provider (Supabase Auth, Clerk, Auth0, ...).

unMeet does not store passwords. The provider signs a JWT; we check the signature, issuer,
audience and expiry and read the user's email from it. Keys come either from a shared secret
(HS256, e.g. Supabase's JWT secret) or from the provider's JWKS endpoint (RS256/ES256, e.g.
Clerk, Auth0, newer Supabase projects). Which provider to use is a deployment decision: nothing
here depends on a specific one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import jwt


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    subject: str
    email: str


class TokenVerifier(Protocol):
    def verify(self, token: str) -> TokenClaims: ...


class JwtVerifier:
    def __init__(
        self,
        secret: str | None = None,
        jwks_url: str | None = None,
        issuer: str | None = None,
        audience: str | None = None,
        algorithms: tuple[str, ...] | None = None,
        leeway_seconds: int = 30,
    ) -> None:
        if bool(secret) == bool(jwks_url):
            raise ValueError("configure exactly one of a JWT secret or a JWKS URL")
        if secret and not algorithms:
            algorithms = ("HS256",)
        self._secret = secret
        self._jwks_client = jwt.PyJWKClient(jwks_url) if jwks_url else None
        self._issuer = issuer
        self._audience = audience
        self._algorithms = list(algorithms or ("RS256", "ES256"))
        self._leeway = leeway_seconds
        if any(algorithm.lower() == "none" for algorithm in self._algorithms):
            raise ValueError("the 'none' algorithm is not allowed")

    def verify(self, token: str) -> TokenClaims:
        try:
            key: Any = self._secret
            if self._jwks_client is not None:
                key = self._jwks_client.get_signing_key_from_jwt(token).key
            required = ["exp", "sub"]
            payload = jwt.decode(
                token,
                key,
                algorithms=self._algorithms,
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway,
                options={
                    "require": required,
                    "verify_aud": self._audience is not None,
                    "verify_iss": self._issuer is not None,
                },
            )
        except jwt.PyJWTError as error:
            raise InvalidTokenError(str(error)) from error
        subject = payload.get("sub")
        email = payload.get("email")
        if not isinstance(subject, str) or not subject:
            raise InvalidTokenError("token has no subject")
        if not isinstance(email, str) or not email.strip():
            raise InvalidTokenError("token has no email claim")
        if payload.get("email_verified") is False:
            raise InvalidTokenError("email is not verified")
        return TokenClaims(subject=subject, email=email.strip().lower())
