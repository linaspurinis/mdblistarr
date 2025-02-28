# mdblistarr

Companion app for [mdblist.com](https://mdblist.com) for better Radarr and Sonarr integration.

## Docker Hub image

[linaspurinis/mdblistarr](https://hub.docker.com/r/linaspurinis/mdblistarr)

## App Configuration Screen

<img src="https://github.com/linaspurinis/mdblist.doc/raw/main/assets/images/mdblistarr-config-screen.png" width="60%">

## MDBListarr v2-beta

```sh
git clone --branch v2-beta git@github.com:linaspurinis/mdblistarr.git
docker build -t mdblistarr .
docker run -e PORT=5353 -p 5353:5353 mdblistarr
```

```
version: '3'
services:
  mdblistarr:
    container_name: mdblistarr
    image: linaspurinis/mdblistarr:v2-beta
    environment:
      - PORT=5353
    volumes:
      - db:/usr/src/db/
    ports:
      - '5353:5353'
volumes:
  db:
```