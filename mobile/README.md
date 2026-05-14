# PaperReader Android Client

This is the Android-only mobile client for the `web-branch` cloud backend.

## Run Locally

```bash
cd mobile
npm install
npm run android
```

The default API endpoint is:

```text
http://120.26.173.133/api
```

Android cleartext HTTP is enabled for this early test build. Once the server has a domain and HTTPS, change `API_BASE_URL` in `App.tsx` to the HTTPS API URL and remove the cleartext allowance from `app.json`.

## Current Scope

Implemented:

- Login and registration with mobile bearer token storage.
- Task list and pull-to-refresh.
- Task creation using the account's default template.
- Add papers by title.
- Upload local PDF files.
- Paper detail with interpretation content.
- Paper chat.
- Open available PDFs through a short-lived mobile PDF link.
- Deep Research auto-task creation.
- Collections list, create/delete, re-read, and paper membership management.
- Per-user Qwen / Alibaba Cloud Model Studio API key management.
- Deep Research self-check.

Not yet implemented:

- Packs download/build/upload UI.
- Push notifications.
- Offline cache.

The mobile app shares the same backend data model as the web app. It does not create a separate mobile database.
