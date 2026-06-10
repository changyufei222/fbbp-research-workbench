from __future__ import annotations

import base64
import json
import hmac
import os
from typing import Any, Mapping


def _auth_config(config: dict[str, Any] | None) -> dict[str, Any]:
    return (config or {}).get("auth") if isinstance((config or {}).get("auth"), dict) else {}


def auth_enabled(config: dict[str, Any] | None = None) -> bool:
    auth = _auth_config(config)
    oidc = _oidc_config(config)
    return bool(auth.get("enabled")) or bool(oidc.get("enabled")) or bool(os.environ.get(str(auth.get("api_key_env") or "FBBP_A2A_API_KEY")))


def _configured_keys(config: dict[str, Any] | None = None) -> list[str]:
    auth = _auth_config(config)
    keys = [str(item) for item in auth.get("api_keys", []) if str(item)]
    env_name = str(auth.get("api_key_env") or "FBBP_A2A_API_KEY")
    if os.environ.get(env_name):
        keys.append(str(os.environ[env_name]))
    return keys


def _oidc_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    auth = _auth_config(config)
    oidc = auth.get("oidc")
    return oidc if isinstance(oidc, dict) else {}


def _decode_unverified_jwt(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("token is not a JWT")
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode((payload + padding).encode("ascii"))
    parsed = json.loads(decoded.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("JWT payload must be an object")
    return parsed


def _header_value(headers: Mapping[str, str], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return str(value)
    return ""


def extract_api_key(headers: Mapping[str, str], config: dict[str, Any] | None = None) -> str:
    auth = _auth_config(config)
    header_names = auth.get("header_names") or ["Authorization", "X-A2A-API-Key", "X-FBBP-A2A-API-Key"]
    for header in header_names:
        value = _header_value(headers, str(header)).strip()
        if not value:
            continue
        if str(header).lower() == "authorization" and value.lower().startswith("bearer "):
            return value.split(" ", 1)[1].strip()
        return value
    return ""


def extract_bearer_token(headers: Mapping[str, str]) -> str:
    value = _header_value(headers, "Authorization").strip()
    if value.lower().startswith("bearer "):
        return value.split(" ", 1)[1].strip()
    return ""


def authenticate_oidc_headers(headers: Mapping[str, str], config: dict[str, Any] | None = None) -> tuple[bool, str]:
    oidc = _oidc_config(config)
    if not bool(oidc.get("enabled")):
        return False, "oidc_disabled"

    trust_proxy_headers = bool(oidc.get("trust_proxy_headers"))
    if trust_proxy_headers:
        user_header = str(oidc.get("user_header") or "X-Forwarded-User")
        groups_header = str(oidc.get("groups_header") or "X-Forwarded-Groups")
        user = _header_value(headers, user_header).strip()
        if not user:
            return False, "missing_oidc_proxy_user"
        required_groups = [str(item) for item in oidc.get("required_groups", []) if str(item)]
        if required_groups:
            groups = {item.strip() for item in _header_value(headers, groups_header).replace(";", ",").split(",") if item.strip()}
            if not any(group in groups for group in required_groups):
                return False, "missing_required_oidc_group"
        return True, "oidc_proxy_authenticated"

    token = extract_bearer_token(headers)
    if not token:
        return False, "missing_oidc_bearer"

    verify_signature = bool(oidc.get("verify_signature"))
    if verify_signature:
        return False, "oidc_signature_verification_not_configured"

    try:
        claims = _decode_unverified_jwt(token)
    except Exception:
        return False, "invalid_oidc_jwt"

    issuer = oidc.get("issuer")
    audience = oidc.get("audience")
    if issuer and claims.get("iss") != issuer:
        return False, "invalid_oidc_issuer"
    aud_claim = claims.get("aud")
    if audience:
        audiences = aud_claim if isinstance(aud_claim, list) else [aud_claim]
        if audience not in audiences:
            return False, "invalid_oidc_audience"
    required_scopes = [str(item) for item in oidc.get("required_scopes", []) if str(item)]
    if required_scopes:
        scopes = set(str(claims.get("scope") or "").split())
        if not all(scope in scopes for scope in required_scopes):
            return False, "missing_required_oidc_scope"
    return True, "oidc_jwt_claims_authenticated"


def authenticate_headers(headers: Mapping[str, str], config: dict[str, Any] | None = None) -> tuple[bool, str]:
    if not auth_enabled(config):
        return True, "auth_disabled"
    oidc_ok, oidc_reason = authenticate_oidc_headers(headers, config)
    if oidc_ok:
        return oidc_ok, oidc_reason
    provided = extract_api_key(headers, config)
    if not provided:
        return False, oidc_reason if oidc_reason not in {"oidc_disabled", "missing_oidc_bearer"} else "missing_api_key"
    for expected in _configured_keys(config):
        if hmac.compare_digest(provided, expected):
            return True, "authenticated"
    return False, "invalid_api_key"


def auth_metadata(config: dict[str, Any] | None = None) -> dict[str, Any]:
    auth = _auth_config(config)
    oidc = _oidc_config(config)
    enabled = auth_enabled(config)
    schemes = ["Bearer", "ApiKey"] if enabled else []
    if bool(oidc.get("enabled")) and "OIDC" not in schemes:
        schemes.append("OIDC")
    return {
        "enabled": enabled,
        "schemes": schemes,
        "header_names": auth.get("header_names") or ["Authorization", "X-A2A-API-Key", "X-FBBP-A2A-API-Key"],
        "api_key_env": auth.get("api_key_env") or "FBBP_A2A_API_KEY",
        "oidc": {
            "enabled": bool(oidc.get("enabled")),
            "issuer": oidc.get("issuer"),
            "audience": oidc.get("audience"),
            "trust_proxy_headers": bool(oidc.get("trust_proxy_headers")),
            "verify_signature": bool(oidc.get("verify_signature")),
        },
    }
