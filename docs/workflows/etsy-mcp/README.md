# Etsy MCP Server Tutorial

This guide walks you through setting up the Etsy MCP server in this repository so Claude can connect to your Etsy shop.

The goal is not just to read Etsy docs. The goal is to give Claude a real merchant-ops tool layer for Etsy, starting with OAuth connection, shop discovery, listings, receipts, payments, and shop sections.

## What This Server Does

This Etsy MCP server sits between Claude and the Etsy Open API.

The flow looks like this:

`Claude -> your Etsy MCP server -> Etsy Open API -> your Etsy shop`

That means Claude does not connect directly to Etsy on its own. Your MCP server exposes Etsy tools, manages OAuth tokens, and forwards requests to Etsy.

## What You Need

You need an Etsy shop, an Etsy developer app, Python 3.11 or newer, and an MCP client that can connect to a remote MCP endpoint such as Claude Desktop.

You also need:

- an Etsy app API key
- a registered HTTPS redirect URI in your Etsy app settings
- a place to host the MCP server if you want to access it remotely, such as Railway

## Important Difference From Shopify

Etsy does not work like the simple Shopify custom-app token flow.

Shopify can be easy to bootstrap with a long-lived Admin token. Etsy Open API v3 uses OAuth 2.0 Authorization Code flow with PKCE. In practice, that means:

- you create an Etsy app first
- you generate an authorization URL
- you approve the app in a browser
- you copy the authorization code from the redirect URL
- the MCP server exchanges that code for access and refresh tokens
- the server auto-refreshes the Etsy access token later

## Step 1: Create Your Etsy Developer App

Go to [Etsy Developers](https://www.etsy.com/developers/register) and create an app.

After approval, open your app details and copy:

- the API key keystring
- the shared secret, if you want to keep it handy

You also need to add a redirect URI in the app settings. Etsy requires an exact HTTPS redirect URI match.

If you want a quick no-code callback catcher for testing, many builders use a tool like Postman's callback URL. If you do that, make sure the exact URI is registered in your Etsy app settings and matches what you pass to the MCP server.

## Step 2: Create Your Etsy Environment File

Copy the Etsy example environment file:

```bash
cp env.etsy.example .env.etsy
```

Then open `.env.etsy` and fill in at least:

```env
ETSY_API_KEY=your_etsy_app_keystring
ETSY_REDIRECT_URI=https://your-registered-redirect-uri
```

You can leave the token values empty at first. The MCP tools will help you generate them.

## Step 3: Start The Etsy MCP Server

Run:

```bash
set -a
source .env.etsy
set +a
python3 etsy_server.py
```

If the server starts correctly, the MCP endpoint will be:

```text
http://localhost:8000/mcp
```

## Step 4: Connect Claude To The Etsy MCP Server

Add a remote MCP server in Claude Desktop and point it to:

```text
http://localhost:8000/mcp
```

Once connected, Claude should be able to call the Etsy tools exposed by this server.

## Step 5: Complete OAuth Inside Claude

Use the tools in this order:

1. `etsy_connection_status`
2. `etsy_begin_oauth`
3. open the returned `authorization_url` in your browser
4. approve the Etsy app
5. copy the `code` query parameter from the redirect URL
6. run `etsy_exchange_auth_code` with that `code` and the `code_verifier` from step 2
7. run `etsy_get_my_shops`
8. run `etsy_get_shop`

After code exchange, the server stores tokens in the file configured by `ETSY_TOKEN_FILE`, which defaults to `.etsy_tokens.json`.

## Core Tools Included In This MVP

This first Etsy MCP version includes:

- `etsy_begin_oauth`
- `etsy_exchange_auth_code`
- `etsy_refresh_access_token`
- `etsy_connection_status`
- `etsy_set_shop_id`
- `etsy_get_my_shops`
- `etsy_get_shop`
- `etsy_list_listings`
- `etsy_get_listing`
- `etsy_list_receipts`
- `etsy_get_receipt`
- `etsy_list_payments`
- `etsy_list_shop_sections`
- `etsy_create_shop_section`

This is enough to connect Claude, inspect a shop, read listings and orders, and start building merchant workflows on top.

## Example Prompts

Once connected, try prompts like:

```text
Show me my Etsy shop details
List my active Etsy listings
Show me the latest Etsy receipts
List my Etsy shop sections
Create a new Etsy shop section called Seasonal Gifts
```

## Deploying Remotely

If you want Claude to reach this server outside your laptop, deploy it with `Dockerfile.etsy` instead of the Shopify Dockerfile.

On Railway or another container host, set the same Etsy environment variables there and run `python3 etsy_server.py` as the start command if needed.

## Current Scope

This first version is intentionally practical rather than huge. It focuses on:

- connection
- token management
- shop discovery
- listings
- receipts
- payments
- shop sections

You can expand it later with listing creation, inventory, shipping, and other merchant-side actions once the auth and basic shop access are stable.
