# Docker

### 1. Download the Compose file and `.env.example`

```bash
wget https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/refs/heads/main/compose.yml
wget https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/refs/heads/main/.env.example
```

### 2. Prepare the environment and folders

```bash
mkdir -p data
mv .env.example .env
```

- The application runs as a non-root user by default, so the `data` folder must be created beforehand.
- You can change `user: uid:gid` to match your host permissions.

### 3. Configure the environment

- Use a text editor such as `vim` or `nano` to review both the `environment` section in `compose.yml` and `.env`. The default configuration should be sufficient for most use cases.

Two images are available:

- `vttc08/demucs-karaoke-app` is the default image used by `compose.yml`.
- `vttc08/demucs-karaoke-app:vocal-sync` is a larger image that includes `numpy` and `scipy`, which are required for the vocal sync workflow.

!!! note

    Musixmatch and Last.fm tokens are required for the best lyrics experience. Without them, lyrics functionality will be degraded.

- [Last.fm token](https://www.last.fm/api/authentication)
- Musixmatch token (desktop app required): [follow this guide](https://spicetify.app/docs/faq#sometimes-popup-lyrics-andor-lyrics-plus-seem-to-not-work)

### 4. Start the application

```bash
docker compose up -d
docker compose logs -f
```

### 5. Configure the admin user and default presets

```bash
docker compose exec -it karaoke python scripts/admin_user.py create --username admin
docker compose exec -it karaoke python scripts/default_presets.py
```

Once the application is running, open `http://<your-server-ip>:8000/login` and log in with the admin user you just created.

## Next Steps

- [Backup, restore, and upgrade](backup-and-restore.md)
- [Deploy the Demucs service (optional)](demucs-service.md)
- [Connect clients](clients.md)
- [Queue page](../features/queue-page.md)
- [Create AI Karaoke](../tasks/create-ai-karaoke.md)
