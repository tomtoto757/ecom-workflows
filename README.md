# Ecom Workflows

This repository is a home for reusable ecommerce workflows.

Each workflow can have its own tools, setup steps, operating notes, and tutorial. Instead of putting every instruction into one long page, the repository is organized so the front page helps people find the right workflow first, then follow a dedicated guide for that workflow.

## Start Here

If this is your first time in the repo, read this page first. It explains how the repository is structured and where each workflow tutorial lives.

If you already know which workflow you want, open the matching tutorial from the library below.

## Workflow Library

| Workflow | What it does | Tutorial | Status |
| --- | --- | --- | --- |
| Shopify MCP Server | Connects an MCP client to Shopify so you can work with products, orders, customers, collections, inventory, and fulfillments using natural language | [Open tutorial](docs/workflows/shopify-mcp/README.md) | Ready |
| Etsy MCP Server | Connects an MCP client to Etsy so you can authorize against the Etsy Open API and work with shop details, listings, receipts, payments, and sections using natural language | [Open tutorial](docs/workflows/etsy-mcp/README.md) | MVP |

## How This Repository Is Organized

The repository is designed to grow. As more workflows are added, each one should keep its own tutorial, notes, and implementation details close together.

```text
ecom-workflows/
  README.md
  docs/
    workflows/
      shopify-mcp/
        README.md
      etsy-mcp/
        README.md
  server.py
  etsy_server.py
  requirements.txt
  Dockerfile
  Dockerfile.etsy
  env.example
  env.etsy.example
```

The homepage stays short and easy to scan.

Each workflow gets its own document folder so future tutorials do not compete for space on the main page.

The implementation files can stay in the project root for now, and later you can split them by workflow if the repository grows into multiple runnable services.

## How To Use This Repo

1. Open the workflow library and choose the workflow you want.
2. Read that workflow's tutorial from top to bottom once before setting anything up.
3. Follow the setup section exactly, especially the environment variable names.
4. Test the workflow locally before deploying it anywhere public.
5. Save the tutorial link when sharing the workflow with someone else, so they land on the right guide immediately.

## Writing Future Tutorials

To keep the repository readable, every future workflow tutorial should follow the same shape.

Start with a short explanation of what the workflow is for.

Then explain what someone needs before they begin.

After that, walk through setup in the exact order someone will do it in real life.

Close with a section on day to day usage, common mistakes, and troubleshooting.

That structure will make the repository feel consistent even when each workflow uses different tools.

## Current Tutorial

The first workflow guide is here:

[Shopify MCP Server tutorial](docs/workflows/shopify-mcp/README.md)
