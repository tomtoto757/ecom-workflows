#!/usr/bin/env python3
"""
Etsy MCP Server — OAuth-backed Etsy Open API access via FastMCP.

This server is designed for merchant-ops style workflows, starting with:
  - OAuth setup helpers
  - shop discovery
  - listings
  - receipts
  - payments
  - shop sections

Authentication model:
  - Etsy Open API v3 uses OAuth 2.0 Authorization Code + PKCE
  - Access tokens last ~1 hour
  - Refresh tokens last longer and can mint new access tokens
"""
import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ETSY_API_KEY = os.environ.get("ETSY_API_KEY", "")
ETSY_SHARED_SECRET = os.environ.get("ETSY_SHARED_SECRET", "")
ETSY_API_KEY_HEADER = os.environ.get("ETSY_API_KEY_HEADER", "")
ETSY_REDIRECT_URI = os.environ.get("ETSY_REDIRECT_URI", "")
ETSY_DEFAULT_SCOPES = os.environ.get(
    "ETSY_SCOPES",
    "shops_r listings_r listings_w transactions_r",
)
ETSY_ACCESS_TOKEN = os.environ.get("ETSY_ACCESS_TOKEN", "")
ETSY_REFRESH_TOKEN = os.environ.get("ETSY_REFRESH_TOKEN", "")
ETSY_SHOP_ID = os.environ.get("ETSY_SHOP_ID", "")
ETSY_TOKEN_FILE = os.environ.get("ETSY_TOKEN_FILE", ".etsy_tokens.json")

PORT = int(os.environ.get("PORT", "8000"))
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "streamable-http")

BASE_URL = "https://api.etsy.com/v3/application"
OAUTH_AUTHORIZE_URL = "https://www.etsy.com/oauth/connect"
OAUTH_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("etsy_mcp")

mcp = FastMCP("etsy_mcp", host="0.0.0.0", port=PORT, json_response=True)


# ---------------------------------------------------------------------------
# Token store
# ---------------------------------------------------------------------------

class TokenStore:
    """Persists Etsy OAuth tokens locally so the server can auto-refresh them."""

    def __init__(self, token_file: str):
        self._path = Path(token_file).expanduser()
        self._lock = asyncio.Lock()
        self._data: Dict[str, Any] = {
            "access_token": ETSY_ACCESS_TOKEN,
            "refresh_token": ETSY_REFRESH_TOKEN,
            "expires_at": 0,
            "scope": ETSY_DEFAULT_SCOPES,
            "shop_id": ETSY_SHOP_ID,
        }
        self._load()

        if self._data.get("access_token"):
            logger.info("Etsy token store initialized with an existing access token.")
        else:
            logger.warning("No Etsy access token loaded yet. Run the OAuth helper tools first.")

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            stored = json.loads(self._path.read_text())
            if isinstance(stored, dict):
                self._data.update(stored)
        except Exception as exc:
            logger.warning("Could not read Etsy token file %s: %s", self._path, exc)

    def _save_unlocked(self) -> None:
        self._path.write_text(json.dumps(self._data, indent=2))

    def _token_expired(self) -> bool:
        expires_at = float(self._data.get("expires_at") or 0)
        if not self._data.get("access_token"):
            return True
        return time.time() >= max(0, expires_at - 300)

    async def get_access_token(self) -> str:
        if not self._token_expired():
            return str(self._data["access_token"])

        async with self._lock:
            if not self._token_expired():
                return str(self._data["access_token"])

            refresh_token = self._data.get("refresh_token")
            if refresh_token:
                await self._refresh_unlocked()
                return str(self._data["access_token"])

            raise RuntimeError(
                "No valid Etsy access token is available. "
                "Use etsy_begin_oauth and etsy_exchange_auth_code first."
            )

    async def _refresh_unlocked(self) -> None:
        if not ETSY_API_KEY:
            raise RuntimeError("Missing ETSY_API_KEY. Set it before refreshing OAuth tokens.")

        refresh_token = self._data.get("refresh_token")
        if not refresh_token:
            raise RuntimeError("Missing Etsy refresh token. Re-run the OAuth flow.")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                OAUTH_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": ETSY_API_KEY,
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30.0,
            )

        if resp.status_code != 200:
            raise RuntimeError(f"Etsy token refresh failed ({resp.status_code}): {resp.text[:500]}")

        payload = resp.json()
        self._apply_token_payload(payload)
        self._save_unlocked()

    def _apply_token_payload(self, payload: Dict[str, Any]) -> None:
        access_token = payload.get("access_token", "")
        refresh_token = payload.get("refresh_token", self._data.get("refresh_token", ""))
        expires_in = int(payload.get("expires_in", 3600))

        user_id = ""
        if isinstance(access_token, str) and "." in access_token:
            user_id = access_token.split(".", 1)[0]

        self._data.update(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": time.time() + expires_in,
                "token_type": payload.get("token_type", "Bearer"),
                "user_id": user_id,
                "scope": payload.get("scope", self._data.get("scope")),
            }
        )

    async def exchange_code(self, code: str, code_verifier: str, redirect_uri: str) -> Dict[str, Any]:
        if not ETSY_API_KEY:
            raise RuntimeError("Missing ETSY_API_KEY. Set it before exchanging an auth code.")

        async with self._lock:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    OAUTH_TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": ETSY_API_KEY,
                        "redirect_uri": redirect_uri,
                        "code": code,
                        "code_verifier": code_verifier,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=30.0,
                )

            if resp.status_code != 200:
                raise RuntimeError(
                    f"Etsy code exchange failed ({resp.status_code}): {resp.text[:500]}"
                )

            payload = resp.json()
            self._apply_token_payload(payload)
            self._save_unlocked()
            return self.snapshot()

    async def refresh(self) -> Dict[str, Any]:
        async with self._lock:
            await self._refresh_unlocked()
            return self.snapshot()

    async def set_shop_id(self, shop_id: int) -> None:
        async with self._lock:
            self._data["shop_id"] = int(shop_id)
            self._save_unlocked()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "token_file": str(self._path),
            "has_access_token": bool(self._data.get("access_token")),
            "has_refresh_token": bool(self._data.get("refresh_token")),
            "expires_at": self._data.get("expires_at"),
            "user_id": self._data.get("user_id"),
            "shop_id": self._data.get("shop_id"),
            "scope": self._data.get("scope"),
        }

    def configured_shop_id(self) -> Optional[int]:
        shop_id = self._data.get("shop_id")
        return int(shop_id) if shop_id else None

    def user_id(self) -> Optional[int]:
        user_id = self._data.get("user_id")
        return int(user_id) if user_id else None


token_store = TokenStore(ETSY_TOKEN_FILE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api_key_header() -> str:
    if ETSY_API_KEY_HEADER:
        return ETSY_API_KEY_HEADER
    if ETSY_API_KEY and ETSY_SHARED_SECRET:
        return f"{ETSY_API_KEY}:{ETSY_SHARED_SECRET}"
    if ETSY_API_KEY:
        return ETSY_API_KEY
    raise RuntimeError("Missing Etsy API key configuration. Set ETSY_API_KEY at minimum.")


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


async def _headers(authenticated: bool = True) -> Dict[str, str]:
    headers = {
        "x-api-key": _api_key_header(),
        "Content-Type": "application/json",
    }
    if authenticated:
        headers["Authorization"] = f"Bearer {await token_store.get_access_token()}"
    return headers


async def _request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    form: Optional[Dict[str, Any]] = None,
    authenticated: bool = True,
    retry_on_refresh: bool = True,
) -> Dict[str, Any]:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    headers = await _headers(authenticated=authenticated)
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method,
            url,
            params=params,
            json=body,
            data=form,
            headers=headers,
            timeout=45.0,
        )

    if resp.status_code == 401 and authenticated and retry_on_refresh:
        await token_store.refresh()
        return await _request(
            method,
            path,
            params=params,
            body=body,
            form=form,
            authenticated=authenticated,
            retry_on_refresh=False,
        )

    if resp.status_code >= 400:
        detail = resp.text[:1000]
        raise RuntimeError(f"Etsy API error {resp.status_code}: {detail}")

    if not resp.text:
        return {}

    return resp.json()


def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _error(exc: Exception) -> str:
    if isinstance(exc, RuntimeError):
        return str(exc)
    if isinstance(exc, httpx.TimeoutException):
        return "Request timed out while talking to Etsy."
    return f"Unexpected error: {type(exc).__name__}: {exc}"


async def _resolve_shop_id(shop_id: Optional[int] = None) -> int:
    if shop_id is not None:
        return int(shop_id)

    configured = token_store.configured_shop_id()
    if configured:
        return configured

    user_id = token_store.user_id()
    if not user_id:
        raise RuntimeError(
            "No Etsy shop ID is configured yet. Set ETSY_SHOP_ID or run etsy_get_my_shops first."
        )

    data = await _request("GET", f"users/{user_id}/shops")
    shops = data.get("results", [])
    if not shops:
        raise RuntimeError("No Etsy shops were returned for the authenticated user.")

    first_shop = shops[0]
    discovered = int(first_shop["shop_id"])
    await token_store.set_shop_id(discovered)
    return discovered


# ---------------------------------------------------------------------------
# OAuth tools
# ---------------------------------------------------------------------------

class BeginOAuthInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    redirect_uri: Optional[str] = Field(
        default=None,
        description="Exact HTTPS redirect URI registered in your Etsy app settings.",
    )
    scopes: Optional[str] = Field(
        default=None,
        description="Space-separated scopes. Defaults to ETSY_SCOPES.",
    )


@mcp.tool(
    name="etsy_begin_oauth",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def etsy_begin_oauth(params: BeginOAuthInput) -> str:
    """Generate an Etsy OAuth authorization URL plus the PKCE values needed for code exchange."""
    try:
        if not ETSY_API_KEY:
            raise RuntimeError("Missing ETSY_API_KEY. Create an Etsy app first and set its keystring.")

        redirect_uri = params.redirect_uri or ETSY_REDIRECT_URI
        if not redirect_uri:
            raise RuntimeError(
                "Missing redirect URI. Set ETSY_REDIRECT_URI or pass redirect_uri to this tool."
            )

        scopes = params.scopes or ETSY_DEFAULT_SCOPES
        verifier = _pkce_verifier()
        challenge = _pkce_challenge(verifier)
        state = secrets.token_urlsafe(24)

        query = urlencode(
            {
                "response_type": "code",
                "client_id": ETSY_API_KEY,
                "redirect_uri": redirect_uri,
                "scope": scopes,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )

        return _fmt(
            {
                "authorization_url": f"{OAUTH_AUTHORIZE_URL}?{query}",
                "state": state,
                "code_verifier": verifier,
                "code_challenge": challenge,
                "redirect_uri": redirect_uri,
                "scopes": scopes.split(),
                "instructions": [
                    "Open authorization_url in a browser.",
                    "Approve the Etsy app.",
                    "Copy the 'code' query parameter from the redirect URL.",
                    "Run etsy_exchange_auth_code with the code and code_verifier.",
                ],
            }
        )
    except Exception as exc:
        return _error(exc)


class ExchangeAuthCodeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    code: str = Field(..., min_length=1, description="The authorization code from Etsy.")
    code_verifier: str = Field(..., min_length=43, description="PKCE verifier from etsy_begin_oauth.")
    redirect_uri: Optional[str] = Field(default=None, description="Must exactly match the original redirect URI.")


@mcp.tool(
    name="etsy_exchange_auth_code",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def etsy_exchange_auth_code(params: ExchangeAuthCodeInput) -> str:
    """Exchange an Etsy authorization code for access and refresh tokens, then persist them locally."""
    try:
        redirect_uri = params.redirect_uri or ETSY_REDIRECT_URI
        if not redirect_uri:
            raise RuntimeError(
                "Missing redirect URI. Set ETSY_REDIRECT_URI or pass redirect_uri to this tool."
            )

        snapshot = await token_store.exchange_code(
            code=params.code,
            code_verifier=params.code_verifier,
            redirect_uri=redirect_uri,
        )
        return _fmt(
            {
                "status": "connected",
                "token_store": snapshot,
                "next_step": "Run etsy_get_my_shops to discover your shop_id, then etsy_get_shop.",
            }
        )
    except Exception as exc:
        return _error(exc)


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@mcp.tool(
    name="etsy_refresh_access_token",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def etsy_refresh_access_token(params: EmptyInput) -> str:
    """Refresh the Etsy OAuth access token using the stored refresh token."""
    try:
        snapshot = await token_store.refresh()
        return _fmt(snapshot)
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="etsy_connection_status",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def etsy_connection_status(params: EmptyInput) -> str:
    """Inspect the current Etsy token state and local configuration."""
    try:
        return _fmt(
            {
                "connected": token_store.snapshot()["has_access_token"],
                "token_store": token_store.snapshot(),
                "configured": {
                    "has_api_key": bool(ETSY_API_KEY),
                    "has_redirect_uri": bool(ETSY_REDIRECT_URI),
                    "api_key_header_uses_secret": bool(ETSY_SHARED_SECRET or ETSY_API_KEY_HEADER),
                },
            }
        )
    except Exception as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Etsy merchant tools
# ---------------------------------------------------------------------------

class SetShopInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shop_id: int = Field(..., description="Your Etsy numeric shop_id.")


@mcp.tool(
    name="etsy_set_shop_id",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def etsy_set_shop_id(params: SetShopInput) -> str:
    """Persist the Etsy shop_id locally so future tools don't need it every time."""
    try:
        await token_store.set_shop_id(params.shop_id)
        return _fmt({"shop_id": params.shop_id, "status": "saved"})
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="etsy_get_my_shops",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def etsy_get_my_shops(params: EmptyInput) -> str:
    """List the authenticated user's Etsy shops and save the first shop_id for convenience."""
    try:
        user_id = token_store.user_id()
        if not user_id:
            raise RuntimeError("No Etsy user_id available yet. Complete OAuth first.")

        data = await _request("GET", f"users/{user_id}/shops")
        shops = data.get("results", [])
        if shops:
            await token_store.set_shop_id(int(shops[0]["shop_id"]))
        return _fmt({"count": len(shops), "shops": shops, "saved_shop_id": token_store.configured_shop_id()})
    except Exception as exc:
        return _error(exc)


class ShopInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shop_id: Optional[int] = Field(default=None, description="Optional numeric Etsy shop_id.")


@mcp.tool(
    name="etsy_get_shop",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def etsy_get_shop(params: ShopInput) -> str:
    """Get core Etsy shop details for the connected merchant account."""
    try:
        shop_id = await _resolve_shop_id(params.shop_id)
        data = await _request("GET", f"shops/{shop_id}")
        return _fmt(data)
    except Exception as exc:
        return _error(exc)


class ListListingsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    shop_id: Optional[int] = Field(default=None)
    state: Optional[str] = Field(default=None, description="draft, active, inactive, sold_out, expired, etc.")
    limit: Optional[int] = Field(default=25, ge=1, le=100)
    offset: Optional[int] = Field(default=0, ge=0)
    sort_on: Optional[str] = Field(default=None, description="created, price, score, updated, end_time")
    sort_order: Optional[str] = Field(default=None, description="up or down")


@mcp.tool(
    name="etsy_list_listings",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def etsy_list_listings(params: ListListingsInput) -> str:
    """List Etsy listings for a shop, optionally filtered by state."""
    try:
        shop_id = await _resolve_shop_id(params.shop_id)
        query: Dict[str, Any] = {"limit": params.limit, "offset": params.offset}
        for field in ["state", "sort_on", "sort_order"]:
            value = getattr(params, field)
            if value is not None:
                query[field] = value
        data = await _request("GET", f"shops/{shop_id}/listings", params=query)
        results = data.get("results", [])
        return _fmt({"count": len(results), "results": results, "pagination": data.get("pagination")})
    except Exception as exc:
        return _error(exc)


class GetListingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: int = Field(..., description="Numeric Etsy listing_id.")


@mcp.tool(
    name="etsy_get_listing",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def etsy_get_listing(params: GetListingInput) -> str:
    """Get detailed information for a specific Etsy listing."""
    try:
        data = await _request("GET", f"listings/{params.listing_id}")
        return _fmt(data)
    except Exception as exc:
        return _error(exc)


class ListReceiptsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shop_id: Optional[int] = Field(default=None)
    limit: Optional[int] = Field(default=25, ge=1, le=100)
    offset: Optional[int] = Field(default=0, ge=0)
    was_paid: Optional[bool] = Field(default=None)
    was_shipped: Optional[bool] = Field(default=None)
    was_delivered: Optional[bool] = Field(default=None)


@mcp.tool(
    name="etsy_list_receipts",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def etsy_list_receipts(params: ListReceiptsInput) -> str:
    """List Etsy shop receipts (orders) for the connected shop."""
    try:
        shop_id = await _resolve_shop_id(params.shop_id)
        query: Dict[str, Any] = {"limit": params.limit, "offset": params.offset}
        for field in ["was_paid", "was_shipped", "was_delivered"]:
            value = getattr(params, field)
            if value is not None:
                query[field] = value
        data = await _request("GET", f"shops/{shop_id}/receipts", params=query)
        results = data.get("results", [])
        return _fmt({"count": len(results), "results": results, "pagination": data.get("pagination")})
    except Exception as exc:
        return _error(exc)


class GetReceiptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shop_id: Optional[int] = Field(default=None)
    receipt_id: int = Field(..., description="Numeric Etsy receipt_id.")


@mcp.tool(
    name="etsy_get_receipt",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def etsy_get_receipt(params: GetReceiptInput) -> str:
    """Get a specific Etsy receipt by receipt_id."""
    try:
        shop_id = await _resolve_shop_id(params.shop_id)
        data = await _request("GET", f"shops/{shop_id}/receipts/{params.receipt_id}")
        return _fmt(data)
    except Exception as exc:
        return _error(exc)


class ListPaymentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shop_id: Optional[int] = Field(default=None)
    limit: Optional[int] = Field(default=25, ge=1, le=100)
    offset: Optional[int] = Field(default=0, ge=0)


@mcp.tool(
    name="etsy_list_payments",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def etsy_list_payments(params: ListPaymentsInput) -> str:
    """List Etsy payments posted to the connected shop."""
    try:
        shop_id = await _resolve_shop_id(params.shop_id)
        data = await _request(
            "GET",
            f"shops/{shop_id}/payments",
            params={"limit": params.limit, "offset": params.offset},
        )
        results = data.get("results", [])
        return _fmt({"count": len(results), "results": results, "pagination": data.get("pagination")})
    except Exception as exc:
        return _error(exc)


class ListSectionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shop_id: Optional[int] = Field(default=None)


@mcp.tool(
    name="etsy_list_shop_sections",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def etsy_list_shop_sections(params: ListSectionsInput) -> str:
    """List sections in the connected Etsy shop."""
    try:
        shop_id = await _resolve_shop_id(params.shop_id)
        data = await _request("GET", f"shops/{shop_id}/sections")
        results = data.get("results", [])
        return _fmt({"count": len(results), "results": results})
    except Exception as exc:
        return _error(exc)


class CreateSectionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    shop_id: Optional[int] = Field(default=None)
    title: str = Field(..., min_length=1, max_length=255, description="Name of the Etsy shop section.")


@mcp.tool(
    name="etsy_create_shop_section",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def etsy_create_shop_section(params: CreateSectionInput) -> str:
    """Create a new Etsy shop section."""
    try:
        shop_id = await _resolve_shop_id(params.shop_id)
        data = await _request(
            "POST",
            f"shops/{shop_id}/sections",
            form={"title": params.title},
        )
        return _fmt(data)
    except Exception as exc:
        return _error(exc)


if __name__ == "__main__":
    mcp.run(transport=MCP_TRANSPORT)
