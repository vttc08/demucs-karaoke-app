## Fenêtres { #windows }

Ce document couvre l'installation de l'application principale karaoké sur Windows, pour le service Demucs, se référer à [Services aux entreprises](demucs-service.md).

### 1. Télécharger Python/UV et dépendances { #1-download-pythonuv-and-dependencies }

- [Python](https://www.python.org/downloads/windows/) 3.11 ou plus tard, assurez-vous de vérifier "Ajouter Python à PATH" lors de l'installation.
- [UV](https://docs.astral.sh/uv/getting-started/installation/)
- [ffmpeg](https://ffmpeg.org/download.html) 6.0 ou une version ultérieure, ajouter à PATH.
- [Deno](https://docs.deno.com/runtime/getting_started/installation/) ajouter à PATH, seulement si nécessaire.

### 2. Ajouter un binaire à PATH { #2-add-binary-to-path }

Ouvrez « Modifier les variables d'environnement système » et ajoutez ce qui suit à PATH :

- `C:\Tools\ffmpeg\bin` (ou partout où vous avez installé ffmpeg, ffprobe et ffplay.exe)
- chemin Deno si nécessaire, par exemple `C:\Tools\deno`

Vérifier sur la ligne de commande :

```powershell
ffmpeg -version
uv --version
deno --version  # only if needed
python --version
```

### 3. Télécharger et configurer l'application { #3-download-and-setup-the-application }

```powershell
git clone https://github.com/vttc08/demucs-karaoke-app.git
cd demucs-karaoke-app
uv venv
uv pip install -e .
```

!!! tip
    Si git n'est pas disponible, vous pouvez télécharger le zip de GitHub et l'extraire.

!!! note
    L'installation par défaut n'inclut pas `numpy` et `scipy`, qui sont nécessaires pour [synchronisation vocale](../tasks/create-ai-karaoke.md). Si vous avez besoin d'une synchronisation vocale, installez le `vocal-sync` supplémentaire:

    ```powershell
    uv pip install -e .[vocal-sync]
    ```

### 4. Construire la documentation { #4-build-documentation }

Pour la configuration non-Docker, la documentation statique n'est pas incluse. Il est bon d'exécuter l'application sans elle et d'utiliser le [documentation en ligne](https://vttc08.github.io/demucs-karaoke-app/). Pour construire la documentation, installez `mkdocs` et `mkdocs-material`:

```bash
uv pip install mkdocs mkdocs-material mkdocs-minify-plugin mkdocs-static-i18n
uv run scripts/build_docs.py
```

### 5. Configurer l'environnement { #5-configure-the-environment }

```powershell
cp .env.example .env
```

La configuration d'environnement par défaut devrait fonctionner pour la plupart des cas d'utilisation. Vous pouvez examiner la configuration détaillée dans le [Configuration page](../configuration/settings.md).

### 6. Exécution de la demande { #6-running-the-application }

```powershell
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

Pour le démarrage sans surveillance, utilisez Task Scheduler ou un wrapper de service comme NSSM. Store media, cache, logs et la base SQLite sous un répertoire que le compte de service peut lire et écrire.

### 7. Configurer l'utilisateur admin et les préréglages par défaut { #7-configure-the-admin-user-and-default-presets }

Pendant l'exécution de l'application, ouvrez une autre fenêtre PowerShell dans le répertoire de l'application. Créez le premier utilisateur d'administration et installez les préréglages d'étape par défaut :

```powershell
uv run python scripts/admin_user.py create --username admin
uv run python scripts/default_presets.py
```

Une fois l'application en cours d'exécution, ouvrez `http://<your-server-ip>:8000/login` et connectez-vous avec l'utilisateur administrateur que vous venez de créer.

## Prochaines étapes { #next-steps }

- [Configuration de l'application](../configuration/settings.md)
- [Déployer le service Demucs (facultatif)](demucs-service.md)
- [Clients](clients.md)
- [Explorez la page d'attente](../features/queue-page.md)
