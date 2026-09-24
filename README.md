# doublespeed-plugin

Doublespeed's public product MCP connector for Cursor and compatible MCP clients.

## Doublespeed for Cursor

Connect Cursor to [Doublespeed](https://doublespeed.ai) to create social slideshows and product videos, work with product templates and media, save editable drafts, and share review links.

Marketplace publication is pending. Local installation status is recorded below.

## Connect your account

The plugin declares one hosted Streamable HTTP MCP server at `https://doublespeed.ai/api/mcp`. Cursor supports browser OAuth for remote MCP servers. Sign in with your own Doublespeed account and authorize access when Cursor requests it.

This endpoint exposes only the public product catalog. Staff, internal, and admin-only tools are excluded even when an administrator signs in.

Cursor discovers tool names and schemas live from the hosted server after connecting. This repository contains connector configuration and documentation, not a snapshot of the backend. Backend deployments can update the available public tools without changing this wrapper.

Tools follow the connected user's product-workspace permissions. You need access to a Doublespeed product workspace. Select the product before starting a content workflow. Image and video generation consume existing Doublespeed credits and depend on provider availability. Social-account operations require a configured social account.

No shared API key, OAuth client secret, password, or access token is included in this package. Do not paste credentials into chat. OAuth uses the authorization-code flow with PKCE S256, dynamic client registration, and refresh tokens. Cursor handles the user's OAuth connection; this package provides only the server URL. Generation-provider credentials remain server-side and are not included in this package or its MCP configuration.

## Example requests

- Create a three-slide carousel using a pinned template and my product photos. Save a draft and share a review link.
- Create a silent four-second portrait product video in soft morning light. Save a draft and share a review link.

The first request needs a pinned slideshow template and product photos. For asynchronous generation, check job status before presenting a result. Review drafts before publishing to a social account.

## Local installation for testing

Copy this entire plugin directory into `~/.cursor/plugins/local/doublespeed`. Reload Cursor using `Developer: Reload Window`, then open Customize and confirm that Doublespeed and its MCP server are present. Enable the server and complete the browser sign-in flow when requested.

Verify account identity and product access before trying the example creation workflows. Creating media can consume credits. Cursor enterprise policies may restrict local plugin imports or remote MCP access.

Verified on 2026-09-23 in Cursor 3.21.18: local installation and discovery of 63 tools and 9 resources; `whoami` confirmed a public MCP connection. Reading Acme Demo templates and photos and saving a new slideshow draft succeeded. Draft read-back and review-link creation returned `Access denied` and `Forbidden` under an admin session that did not pass the demo workspace's membership checks. The end-to-end slideshow and video workflows remain unverified in Cursor.

## Connection and data access

This package contains the MCP connection definition and logo. It has no executable scripts, shell hooks, or local filesystem integration.

The following Doublespeed endpoints serve connection, sign-in, and discovery:

- `https://doublespeed.ai/api/mcp`: public product MCP tools.
- `https://doublespeed.ai/api/mcp-info`: public capability information.
- `https://doublespeed.ai/.well-known/oauth-protected-resource`: protected-resource discovery.
- `https://doublespeed.ai/.well-known/oauth-authorization-server`: authorization-server discovery.
- `https://doublespeed.ai/oauth/authorize`: user authorization.
- `https://doublespeed.ai/api/oauth/register`: OAuth client registration.
- `https://doublespeed.ai/api/oauth/token`: code exchange and token refresh.
- `https://doublespeed.ai/login`: account sign-in.

Tool requests send their arguments and the connected account's authorization to Doublespeed. Tools can read workspace records and media, create or change content, and perform social-account actions when configured and explicitly requested. Tool results can contain media and review links for the client to open. Generation providers and other service data handling are described in the [privacy policy](https://doublespeed.ai/privacy).

## Support and license

- [MCP documentation](https://docs.doublespeed.ai/mcp)
- [Support](https://doublespeed.ai/support)
- Publisher contact: ts@doublespeed.ai
- [Terms of service](https://doublespeed.ai/tos)
- [Privacy policy](https://doublespeed.ai/privacy)

The connector configuration and documentation in this package are licensed under the [MIT License](LICENSE), copyright 2026 Doublespeed. Files under `assets/`, including the Doublespeed logo, and Doublespeed branding and trademarks are excluded from this license. No trademark rights are granted.

The MIT license does not cover Doublespeed's hosted service or backend source code. Use of the hosted service remains subject to its terms of service. Doublespeed branding remains the property of its owner.
