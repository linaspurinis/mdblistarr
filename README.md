# mdblistarr

Companion app for [mdblist.com](https://mdblist.com) for better Radarr, Sonarr, and Plex integration.

## Docker Hub image

[linaspurinis/mdblistarr](https://hub.docker.com/r/linaspurinis/mdblistarr)

## Basics

- Connects MDBList with Radarr and Sonarr.
- Uploads your current library state back to MDBList on schedule.
- Pulls MDBList queue items and sends add requests to Radarr/Sonarr.
- Supports multiple Radarr/Sonarr instances, each with its own quality profile, root folder, tags, and (Sonarr) monitor option.
- Optional Plex integration: stamps posters with the mdblist score and age rating, and can sync the mdblist score into Plex's Audience Rating field so you can sort your library by it.
- Login required — the app creates its first administrator account on first run.
- API keys and MDBList tokens are encrypted at rest.
- Runs as a simple Docker container with persistent DB volume.

### Basic workflow

1. On first visit, create the administrator account (or set `MDBLISTARR_ADMIN_USERNAME`/`MDBLISTARR_ADMIN_PASSWORD` beforehand to skip the setup screen — see [Authentication](#authentication)).
2. Connect your MDBList account via OAuth (or enter an API key manually).
3. Add your Radarr and Sonarr instances, including quality profile, root folder, tags, and (Sonarr) monitor option.
4. Let scheduled sync keep MDBList and your ARR apps in sync.

## New in v2.5.0

- **Plex poster badges**: connect a Plex server and mdblistarr stamps each movie/show poster with the mdblist score (top-left, color-coded the same way mdblist.com and the iOS app color it — green/amber/red by score) and age rating (bottom-right). Toggle either badge on/off per Plex server.
- **Smart re-stamping, not brute force**: posters are only redrawn when the mdblist score/age rating or the poster art itself actually changed — a repeat sync is a fast no-op for everything already up to date. The original, un-badged poster is always kept cached so re-stamps never draw badges on top of badges.
- **Optional Audience Rating sync**: overwrite Plex's Audience Rating with the mdblist score (locked, so Plex won't revert it on its own metadata refresh) so you can sort your library by mdblist score. Off by default; the original rating is saved before the first override.
- **Reset to Original**: restores posters and ratings back to what Plex had before mdblistarr touched them, scoped to your currently-selected libraries (same scope as the sync itself).
- **Background sync with live progress**: "Sync Now" runs in the background instead of blocking the page — watch live progress (items processed, stamped/skipped/errors, current title) and cancel a running sync at any point.

- Connect via a Plex PIN-based flow (click "Connect with Plex", authorize on plex.tv) — no manual token copying.

## New in v2.4.0

- **Authentication required**: every page now sits behind login. On first run you're taken to a one-time setup screen to create the administrator account, instead of the previous default `admin`/`admin` credentials created automatically on every boot.
- **Encrypted secrets at rest**: Radarr/Sonarr API keys and MDBList OAuth tokens/API key are now encrypted in the database. A per-install encryption key is generated automatically and persisted under the existing DB volume (`/usr/src/db/secrets/`) — no extra volume needed.
- **Per-instance tags**: pick which Radarr/Sonarr tags get applied to everything added through a given instance, straight from that instance's existing tag list.
- **Sonarr monitor option**: choose the `monitor` behavior (all/future/missing/existing/recent/pilot/firstSeason/latestSeason/none) used when adding a show, per Sonarr instance.
- Fix: `seasonFolder` is now explicitly sent as `true` when adding shows — previously it silently defaulted to `false` via the Sonarr API, so episodes could land outside season folders.
- Fix: the entrypoint no longer runs `makemigrations` on every boot, which could silently drift schema on persistent deployments. Existing databases are reconciled automatically on upgrade.

### Authentication

- On first run, visiting the app redirects to a one-time `/setup` page to create the administrator account.
- To skip the setup screen (e.g. for automated deployments), set `MDBLISTARR_ADMIN_USERNAME` (defaults to `admin`) and `MDBLISTARR_ADMIN_PASSWORD` before first boot.
- **Upgrading an existing deployment**: if your admin account still uses the old default `admin`/`admin` password, it will be disabled on upgrade and you'll be sent through `/setup` again to create a new one — set `MDBLISTARR_ADMIN_PASSWORD` beforehand if you'd rather avoid that. If you'd already changed that password, nothing changes except you'll need to log in once, the same as any first visit after this update.

## New in v2.3.0

- MDBList OAuth authentication: connect your account via the new "Connect with MDBList" button instead of copying an API key. Uses the OAuth 2.0 device authorization flow.
- API key auth still works until you connect via OAuth — once OAuth is connected, the API key is cleared and OAuth takes over.

## New in v2.2.4

- Added support for syncing library status across all configured servers

## New in v2.2.3

- Optional MDBList collection sync: enable "Sync Library Status" in the MDBList config tab to keep your MDBList collection up to date based on what is downloaded in Radarr/Sonarr.
- Configurable sync hour: choose which UTC hour of the day Radarr and Sonarr sync runs. A random hour is assigned automatically on first run to spread load across all users.
- Home page now shows last sync time and next sync estimate so you always know when to expect the next run.
- Fixed UI bug where the Radarr/Sonarr server form would reset after saving — the selected server now stays active across page reloads.

## New in v2.2.2

- Full sync now reports monitored and unmonitored items more reliably:
  - Radarr uses `hasFile` to mark downloaded vs missing.
  - Sonarr uses episode file statistics where available.
- Import list exclusions from Radarr/Sonarr are included in sync payloads.
- If a movie is already in Radarr, MDBListarr now triggers a Radarr `MoviesSearch` command instead of only logging a duplicate error.
- HTTP/JSON handling is more defensive for empty/invalid/compressed responses.

## App Configuration Screen

![image](https://github.com/user-attachments/assets/cdd58b1a-4b55-464d-84dd-55246ba6a096)

## MDBListarr

```sh
git clone --branch latest git@github.com:linaspurinis/mdblistarr.git
docker build -t mdblistarr .
docker run -e PORT=5353 -p 5353:5353 mdblistarr
```

```
services:
  mdblistarr:
    container_name: mdblistarr
    image: linaspurinis/mdblistarr:latest
    environment:
      - PORT=5353
    volumes:
      - db:/usr/src/db/
    ports:
      - '5353:5353'
volumes:
  db:
```

### Reverse proxy / TrueNAS hostnames

If you access MDBListarr through a hostname, custom port, or reverse proxy, set Django's host and CSRF origin values explicitly:

```yaml
environment:
  - PORT=5353
  - CSRF_TRUSTED_ORIGINS=https://mdblistarr.example.com,http://192.168.1.10:5353
```

`CSRF_TRUSTED_ORIGINS` must include the scheme (`http://` or `https://`) and the port when one is used.
