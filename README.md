# mdblistarr

Companion app for [mdblist.com](https://mdblist.com) for better Radarr and Sonarr integration.

## Docker Hub image

[linaspurinis/mdblistarr](https://hub.docker.com/r/linaspurinis/mdblistarr)

## Basics

- Connects MDBList with Radarr and Sonarr.
- Uploads your current library state back to MDBList on schedule.
- Pulls MDBList queue items and sends add requests to Radarr/Sonarr.
- Supports multiple Radarr/Sonarr instances.
- Runs as a simple Docker container with persistent DB volume.

### Basic workflow

1. Configure your MDBList API key in MDBListarr.
2. Add your Radarr and Sonarr instances.
3. Set quality profile and root folder mappings per instance.
4. Let scheduled sync keep MDBList and your ARR apps in sync.

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
