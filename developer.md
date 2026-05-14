# Developer Notes

This repository intentionally uses two long-lived branches:

- `main`: local / desktop-first development branch.
- `web-branch`: cloud deployment branch for the hosted PaperReader service.

Do not treat `web-branch` as a short-lived feature branch. It is the permanent branch for cloud-specific code.

## Branch Strategy

`main` should keep local-machine features and developer convenience features. It can include local-only operations that make sense for a single-user workstation.

`web-branch` should keep cloud-safe behavior. Avoid exposing server maintenance operations in the web UI. In particular, the web branch should not provide a browser button that runs `git pull`, rebuilds the application, restarts services, or otherwise mutates the server deployment.

When a feature is generally useful, implement it on the branch where it is needed first, then cherry-pick or re-implement it on the other branch only if the behavior also makes sense there. Do not blindly merge `main` into `web-branch` or `web-branch` into `main` without checking for branch-specific behavior.

## Current Settings Split

On `web-branch`, Settings contains:

- Self-check: environment and provider availability checks.
- Packs Management: download installed research packs, build local packs when needed, and upload packs to GitHub Releases.
- API Management: configure Gemini, DeepSeek, DashScope, and GitHub credentials.

The web branch intentionally does not include one-click application update from the browser.

## Aliyun Cloud Server

The current cloud target is an Alibaba Cloud ECS instance used for the web deployment of PaperReader.

Known setup from the console/session:

- Product: ECS cloud server.
- Region: China East 1, Hangzhou.
- Operating system: Ubuntu 22.04 64-bit.
- Instance size used for testing: 2 vCPU / 4 GiB memory.
- Disk: ESSD Entry cloud disk, 40 GiB.
- Public bandwidth: 100 Mbps peak.
- Security group currently needs inbound web access configured for the deployed service port.

Operational notes:

- Keep server passwords, API keys, GitHub tokens, and `.env` contents out of git.
- Use the Aliyun console as the source of truth for current public IP, security group, billing, and instance status.
- For cloud deployment updates, use SSH, deployment scripts, or a CI/CD process instead of a web UI update button.
- After pulling cloud code on the server, rebuild the frontend if frontend files changed and restart the backend service if backend code changed.

## Sensitive Data Rules

Never commit:

- `.env` files or provider keys.
- Server root passwords or SSH private keys.
- Local SQLite databases such as `app.db`.
- Screenshots that expose private console data unless they are intentionally sanitized.

Untracked local files in the working tree may be user artifacts. Do not delete or revert them unless explicitly requested.
