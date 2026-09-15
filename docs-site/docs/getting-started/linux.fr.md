# Linux

Le déploiement Linux utilise systemd pour gérer l’application principale. Cette configuration convient aux installations directement sur l’hôte et aux conteneurs LXC.

## Installation

### 1. Préparer l’application et ses dépendances { #1-prepare-the-application-and-dependencies }

Clonez l’application :

```bash
git clone https://github.com/vttc08/demucs-karaoke-app.git /opt/karaoke/app
```

Installez [uv](https://docs.astral.sh/uv/getting-started/installation/), puis les dépendances système et celles de l’application :

```bash
sudo apt-get install ffmpeg
cd /opt/karaoke/app
uv venv
uv pip install -e .
```

!!! note

    L’installation par défaut n’inclut pas `numpy` ni `scipy`, nécessaires à la [synchronisation vocale](../tasks/create-ai-karaoke.md). Pour l’activer, installez l’extra `vocal-sync` :

    ```bash
    uv pip install -e ".[vocal-sync]"
    ```

### 2. Installer Deno si nécessaire

Certaines vidéos nécessitent l’exécution JavaScript externe de yt-dlp. Installez [Deno](https://docs.deno.com/runtime/getting_started/installation/) uniquement dans ce cas. Le paquet npm convient si npm est déjà installé sur l’hôte :

```bash
npm install -g deno
which deno
```

### 3. Construire la documentation

Dans une installation sans Docker, la documentation statique n’est pas incluse par défaut. Vous pouvez lancer l’application sans cette documentation et consulter la [documentation en ligne](https://vttc08.github.io/demucs-karaoke-app/). Pour la construire localement, installez ses dépendances puis exécutez le script de build :

```bash
uv pip install mkdocs mkdocs-material mkdocs-minify-plugin mkdocs-static-i18n pymdown-extensions
uv run scripts/build_docs.py
```

### 4. Configurer l’environnement

Placez l’environnement dans `/etc/karaoke.env`.

La configuration suivante convient à la plupart des installations. Remplacez les chemins d’exemple et l’URL du service par les valeurs correspondant à votre hôte. Consultez la [section consacrée à la configuration](../configuration/settings.md) pour les détails.

```env
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite:////opt/karaoke/data/karaoke.db
MEDIA_PATH=/your/media/path
CACHE_PATH=/opt/karaoke/data/cache
LOG_DIR=/opt/karaoke/data/logs
YTDLP_PATH=yt-dlp
YTDLP_DENO_PATH=/usr/local/bin/deno
DEMUCS_API_URL=http://demucs-host:8001
```

!!! note

    Le répertoire indiqué par `MEDIA_PATH` doit être accessible en lecture et en écriture par l’utilisateur qui exécute l’application et disposer de suffisamment d’espace pour vos médias. Les partages SMB et NFS sont pris en charge.

### 5. Créer le service systemd

Créez `/etc/systemd/system/karaoke.service` avec le contenu suivant :

```ini
[Unit]
Description=Karaoke main app
After=network-online.target
Wants=network-online.target

[Service]
User=<your-user>
Group=<your-group>
WorkingDirectory=/opt/karaoke/app
EnvironmentFile=/etc/karaoke.env
ExecStart=/usr/bin/env uv run uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6. Activer et démarrer le service

```bash
sudo systemctl daemon-reload
sudo systemctl enable karaoke.service
sudo systemctl start karaoke.service
sudo systemctl status karaoke.service
```

Après avoir modifié les chemins des outils ou du stockage dans `/settings`, redémarrez le service si le changement concerne les montages ou l’environnement du processus initialisés au démarrage.

### 7. Configurer le compte administrateur et les préréglages par défaut

Depuis le répertoire de l’application, créez le premier compte administrateur et installez les préréglages de scène par défaut :

```bash
cd /opt/karaoke/app
uv run python scripts/admin_user.py create --username admin
uv run python scripts/default_presets.py
```

Une fois l’application démarrée, ouvrez `http://<your-server-ip>:8000/login` et connectez-vous avec le compte créé.

## Étapes suivantes

- [Sauvegarder, restaurer et mettre à niveau](backup-and-restore.md)
- [Déployer le service Demucs (facultatif)](demucs-service.md)
- [Connecter les clients](clients.md)
- [Page de file d’attente](../features/queue-page.md)
- [Créer un karaoké avec l’IA](../tasks/create-ai-karaoke.md)
