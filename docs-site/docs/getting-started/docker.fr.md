# Coq { #docker }

### 1. Télécharger le fichier Composer et `.env.example` { #1-download-the-compose-file-and-envexample }

```bash
wget https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/refs/heads/main/compose.yml
wget https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/refs/heads/main/.env.example
```

### 2. Préparer l'environnement et les dossiers { #2-prepare-the-environment-and-folders }

```bash
mkdir -p data
mv .env.example .env
```

- L'application fonctionne comme un utilisateur non root par défaut, de sorte que le dossier `data` doit être créé au préalable.
- Vous pouvez modifier `user: uid:gid` pour correspondre aux autorisations de votre hôte.

### 3. Configurer l'environnement { #3-configure-the-environment }

- Utilisez un éditeur de texte comme `vim` ou `nano` pour examiner la section `environment` dans `compose.yml` et `.env`. La configuration par défaut devrait être suffisante pour la plupart des cas d'utilisation.

Deux images sont disponibles :

- `vttc08/demucs-karaoke-app` est l'image par défaut utilisée par `compose.yml`.
- `vttc08/demucs-karaoke-app:vocal-sync` est une image plus grande qui inclut `numpy` et `scipy`, qui sont nécessaires pour le workflow de synchronisation vocale.

!!! note

    Les jetons Musixmatch et Last.fm sont nécessaires pour la meilleure expérience des paroles. Sans eux, la fonctionnalité des paroles sera dégradée.

    - [Last.fm jeton](https://www.last.fm/api/authentication)
    - Jeton Musixmatch (application de bureau obligatoire): [suivre ce guide](https://spicetify.app/docs/faq#sometimes-popup-lyrics-andor-lyrics-plus-seem-to-not-work)

### 4. Démarrer l'application { #4-start-the-application }

```bash
docker compose up -d
docker compose logs -f
```

### 5. Configurer l'utilisateur administrateur et les préréglages par défaut { #5-configure-the-admin-user-and-default-presets }

```bash
docker compose exec -it karaoke python scripts/admin_user.py create --username admin
docker compose exec -it karaoke python scripts/default_presets.py
```

Une fois l'application en cours d'exécution, ouvrez `http://<your-server-ip>:8000/login` et connectez-vous avec l'utilisateur administrateur que vous venez de créer.

## Prochaines étapes { #next-steps }

- [Sauvegarde, restauration et mise à jour](backup-and-restore.md)
- [Déployer le service Demucs (facultatif)](demucs-service.md)
- [Connecter les clients](clients.md)
- [Demande de renseignements](../features/queue-page.md)
- [Créer AI Karaoke](../tasks/create-ai-karaoke.md)
