# Shopify MCP Server Tutorial

This guide shows you how to set up and use the Shopify MCP workflow in a way that feels predictable, safe, and easy to hand off to someone else later.

The goal of this workflow is simple. You connect an MCP client to a Shopify store, then use natural language to inspect and manage products, orders, customers, collections, inventory, and fulfillments.

If you are adding this workflow for a client, it helps to think of the setup in three stages. First, you prepare Shopify access. Then you run the server locally and make sure it works. Finally, you deploy it and connect it to your MCP client.

## What You Need Before You Begin

Before starting, make sure you have the following ready.

| Item | Why it matters |
| --- | --- |
| Python 3.11 or newer | The server runs in Python |
| A Shopify store | This is the store the workflow will control |
| Permission to create a Shopify custom app | You need this to get an Admin API token |
| A GitHub account | Useful for deployment and sharing |
| A Railway account | The easiest way to publish the server |
| An MCP client such as Claude | This is where you will actually use the workflow |

## What This Workflow Can Do

Once connected, this workflow can help with day to day Shopify operations in plain language.

You can ask for open orders, look up customers, create products, update inventory, inspect collections, or create fulfillments without manually clicking through the Shopify admin for every action.

That makes it a strong fit for ecommerce operators, assistants, support teams, and founders who want to move faster without building a custom dashboard first.

## Step 1: Get Your Shopify Credentials

You need two values for the basic setup.

The first is your store name. This is the part before `.myshopify.com`.

If your admin URL is `https://acme-store.myshopify.com/admin`, your store name is `acme-store`.

The second is an Admin API access token from a Shopify custom app. A normal API key is not enough for this workflow.

Open Shopify Admin, then go to `Settings`, then `Apps and sales channels`.

Open `Develop apps`.

If Shopify asks you to allow custom app development, approve it.

Create a new app and give it a clear name such as `Shopify MCP`.

Open the configuration area for the app and enable the scopes you need. For most setups, these are the useful ones:

`read_products`, `write_products`, `read_orders`, `write_orders`, `read_customers`, `write_customers`, `read_inventory`, `write_inventory`, `read_fulfillments`, `write_fulfillments`, `read_webhooks`, and `write_webhooks`

Save the configuration, install the app, then open the API credentials page.

Reveal the Admin API token and copy it immediately. Shopify only shows this token once.

## Step 2: Install The Workflow Locally

Clone the repository and move into the project folder.

```bash
git clone https://github.com/tomtoto757/ecom-workflows.git
cd ecom-workflows
```

Install the Python dependencies.

```bash
pip install -r requirements.txt
```

## Step 3: Configure Your Environment

Create a local environment file from the example file.

```bash
cp env.example .env
```

Open `.env` and add your Shopify details.

```env
SHOPIFY_STORE=your-store-name
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxx
```

For the simplest setup, those are the only values you need to change.

If you are planning to deploy this workflow, keep the same variable names in your hosting platform so local and cloud environments stay aligned.

## Step 4: Run The Server Locally

Start the server with Python.

```bash
python server.py
```

If everything is configured correctly, the server starts on port `8000` and exposes the MCP endpoint at `http://localhost:8000/mcp`.

At this stage, you are not trying to make the setup look polished. You are only checking that the workflow runs cleanly with real credentials before deployment.

## Step 5: Deploy It So Your MCP Client Can Reach It

An MCP client cannot connect to your local machine unless you expose it somehow, so the easiest production path is to deploy the workflow on Railway.

Sign in to Railway with GitHub.

Create a new project from this repository.

Railway should detect the `Dockerfile` automatically.

Once the service builds, generate a public domain from the Railway networking settings.

Then add the same environment variables you used locally.

| Variable | Value |
| --- | --- |
| `SHOPIFY_STORE` | Your Shopify store name |
| `SHOPIFY_ACCESS_TOKEN` | Your Admin API token |
| `PORT` | `8000` |
| `MCP_TRANSPORT` | `streamable-http` |

After the environment variables are saved, Railway will restart the service.

Your public MCP endpoint will be:

```text
https://your-project-domain.up.railway.app/mcp
```

## Step 6: Connect The Workflow To Your MCP Client

Open your MCP client and add a new remote MCP server.

Use a clear name such as `Shopify Operations`.

Paste in your public endpoint URL.

If you are using Claude, this is the URL you will enter in the integration setup.

Once the connection is live, you can start using the Shopify tools through natural language.

## Step 7: Secure The Endpoint Before Sharing It

If this workflow is only for local testing, leaving the endpoint open for a moment may be acceptable.

If it will be used by a client or kept online, protect it with a bearer token.

Add a `BEARER_TOKEN` environment variable in Railway with a long random value.

Then update the server so it checks the `Authorization` header before serving requests.

After that, enter the same token in your MCP client when it asks for an authentication token.

This token is separate from your Shopify access token. Keeping them separate is important because they solve different problems.

The Shopify token lets the server talk to Shopify.

The bearer token controls who can talk to your server.

## What Day To Day Usage Looks Like

Once the workflow is connected, you can use prompts such as:

```text
Show me all unfulfilled orders from today
Create a draft product called Summer T-Shirt priced at 29.99
Find customers with the email john@example.com
Set the inventory for product 123 at location 456 to 50
```

You do not need to memorize every tool name if your MCP client can surface tools naturally, but it helps to know the workflow covers products, orders, customers, collections, inventory, fulfillments, shop details, and webhooks.

## Common Issues

If authentication fails, the Shopify token is usually wrong, expired, or copied from the wrong app.

If Shopify returns a permission error, the custom app is usually missing one or more required scopes.

If the MCP client cannot connect, the problem is usually the public URL, the missing `/mcp` path, or a missing bearer token in the client.

If you lose the Shopify token, reinstall the custom app and generate a new one.

## Suggested Format For Future Workflow Tutorials

If you add more workflows later, use this same rhythm.

Start by explaining what the workflow is for in plain language.

Then describe what someone needs before they begin.

Walk through setup in the exact order they will perform it.

End with real examples, common mistakes, and operating notes.

That pattern feels much more human than a giant technical dump, and it makes the repository easier to grow without becoming messy.
