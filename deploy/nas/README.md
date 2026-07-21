# Reusable NAS deployment

This profile runs MeTube on a Linux NAS with persistent downloads, optional LAN proxy access, Bilibili direct routing, and automatic yt-dlp nightly updates. It keeps machine-specific values in an untracked `.env` file.

## 1. Prepare the configuration

From the repository root:

```bash
cp deploy/nas/.env.example deploy/nas/.env
```

Edit `deploy/nas/.env` and set at least:

- `METUBE_DOWNLOAD_DIR`: an absolute directory on the NAS.
- `METUBE_PUID` and `METUBE_PGID`: the owner IDs for that directory. Check them with `id -u` and `id -g`.
- `METUBE_HTTP_PROXY` and `METUBE_HTTPS_PROXY`: a proxy URL reachable from the NAS, if the NAS cannot reach a supported site directly.

When the proxy runs on another LAN computer, use that computer's stable LAN IP and enable LAN connections in the proxy application. Reserve the address in DHCP so it does not change after a reboot.

The default `NO_PROXY` sends Bilibili and its media CDN directly from the NAS while allowing sites such as YouTube to use the configured proxy.

## 2. Validate and start

```bash
docker compose --env-file deploy/nas/.env -f deploy/nas/compose.yaml config --quiet
docker compose --env-file deploy/nas/.env -f deploy/nas/compose.yaml pull
docker compose --env-file deploy/nas/.env -f deploy/nas/compose.yaml up -d
docker compose --env-file deploy/nas/.env -f deploy/nas/compose.yaml ps
```

Open `http://NAS_ADDRESS:8081`. Change `METUBE_PORT` if that port is already in use.

## 3. Verify both download paths

Submit one public Bilibili URL and one public YouTube URL in the web UI. Check progress in the Downloading section and confirm the files appear under `METUBE_DOWNLOAD_DIR`.

Useful diagnostics:

```bash
docker logs --tail 100 metube
docker exec metube yt-dlp --version
docker exec metube yt-dlp --simulate --no-playlist 'VIDEO_URL'
```

If Bilibili returns HTTP 412, confirm that it is covered by `METUBE_NO_PROXY` and that a recent yt-dlp nightly was installed. If YouTube reports a proxy connection error, verify that the proxy address is reachable from the NAS and that its LAN IP has not changed.

Use Advanced Options in the MeTube UI to upload `cookies.txt` when a site requires sign-in, membership, age verification, or higher-quality authenticated formats.

## Updating and rollback

The container upgrades yt-dlp nightly at startup and schedules a restart at `METUBE_YTDL_NIGHTLY_UPDATE_TIME`. Update MeTube itself with:

```bash
docker compose --env-file deploy/nas/.env -f deploy/nas/compose.yaml pull
docker compose --env-file deploy/nas/.env -f deploy/nas/compose.yaml up -d
```

Before replacing an existing deployment, keep its Compose file and `.env` as a backup. To stop this profile without deleting downloads:

```bash
docker compose --env-file deploy/nas/.env -f deploy/nas/compose.yaml down
```

MeTube does not provide built-in user authentication. Restrict the listening address, firewall the port, or place it behind an authenticated reverse proxy before exposing it outside a trusted LAN.
