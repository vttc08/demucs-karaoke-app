## Sauvegarde et restauration { #backup-and-restore }
Pour l'application principale, les seules données à sauvegarder sont `karaoke.db` dans le dossier `/data` et l'application conservera toutes les configurations lorsqu'elle sera déplacée ailleurs.
### Coq { #docker }
Exécutez la commande de sauvegarde sur la machine hôte.
```bash
tar -czvf backup.tar.gz -C /path/to/data/ .
```
> Cela suppose que la base de données, le support karaoké et le cache sont tous situés dans le dossier `/data`. Si votre support karaoké est situé ailleurs, sauvegardez ces dossiers en conséquence.

Copier les `compose.yml`, `.env` et `backup.tar.gz` sur la nouvelle machine hôte et restaurer la sauvegarde avec la commande suivante.
```bash
tar -xzvf backup.tar.gz -C /path/to/new/data/
docker compose up -d
```

Optionnel : re-scanner la médiathèque

### Linux/Windows { #linuxwindows }

Même procédure que Docker, sauvegardez le dossier `/data` et restaurez-le sur la nouvelle machine hôte. Si le chemin du dossier est différent, assurez-vous de changer le fichier `MEDIA_PATH` et `CACHE_PATH` dans le fichier `.env` pour pointer vers le nouvel emplacement.

Sous Windows, vous pouvez utiliser `robocopy`.
```powershell
robocopy C:\path\to\data D:\path\to\new\data /E
```

### Démucs { #demucs }

Aucun fichier de base de données/config ne doit être sauvegardé. Le service peut fonctionner en modifiant simplement le fichier `.env`.

Les modèles de téléchargement de l'application, si vous voulez sauvegarder les modèles, si dépend de l'emplacement de votre cache de face de câlin

- SherpaONNX: `<demucs_svc_root>/model_data/sherpa_spleeter`
- Demucs et WhisperX: `$env:HF_HOME` ou `%USERPROFILE%\.cache\huggingface` sous Windows, `~/.cache/huggingface` sous Linux

Les modèles seront téléchargés à nouveau s'ils ne sont pas trouvés, donc il pourrait ne pas être nécessaire de sauvegarder.

## Mise à jour { #upgrade }
### Coq { #docker }
Tirez la dernière image et redémarrez le service.
```bash
docker compose pull
docker compose up -d
docker image prune -f
```
### Linux/Windows/Demucs { #linuxwindowsdemucs }
Téléchargez le dernier code.
```bash
git pull
uv pip install -e . --upgrade
```
Redémarrez le service en utilisant `systemd` ou `services.msc` si nécessaire.
