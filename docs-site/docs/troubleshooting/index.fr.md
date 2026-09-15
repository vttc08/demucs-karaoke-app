# Dépannage { #troubleshooting }

Utilisez cette page pour trouver les problèmes courants et leurs solutions possibles concernant l’application et le service Demucs. Pour les procédures propres à chaque tâche, consultez les [guides destinés aux utilisateurs](../tasks/for-users.md).

## Sommaire { #contents }

- [Application or Demucs is not accessible](#application-or-demucs-is-not-accessible)
    - [Demucs connection fails](#demucs-connection-fails)
- [yt-dlp fails to download](#yt-dlp-fails-to-download)
- [Lyrics cannot be found or are incorrect](#lyrics-cannot-be-found-or-are-incorrect)
- [Vocal separation is very slow](#vocal-separation-is-very-slow)
- [WhisperX alignment fails or takes too long](#whisperx-alignment-fails-or-takes-too-long)
- [WhisperX lyrics are poorly synchronized](#whisperx-lyrics-are-poorly-synchronized)
- [iOS playback issues](#ios-playback-issues)

## Application ou Demucs n'est pas accessible { #application-or-demucs-is-not-accessible }

Si l'application principale n'est pas accessible, vérifiez les éléments suivants.

Vérifiez le [paramètre HOST](../configuration/environments.md#server-and-routing). Une écoute sur localhost ou 127.0.0.1 limite l’accès à la machine hôte. Pour accéder à l’application depuis les autres appareils du réseau local, utilisez l’adresse IP locale de l’hôte. Dans Docker, utilisez 0.0.0.0, car le conteneur dispose de son propre réseau et de sa propre couche NAT.

Check the Docker port mapping. For `-p 8000:8000`, the left side is the host port and the right side is the container port. The host port can be any free port on the machine, but the container port must match the [PORT setting](../configuration/environments.md#server-and-routing).

For example, `-p 8001:8001` will not work if the container is still configured with `PORT=8000`. In that case, use `-p 8001:8000`, or change the `PORT` value to 8001 inside the container.

Vérifiez également que le pare-feu hôte permet le trafic entrant sur le port hôte.

### Permettre l'application via Windows Firewall { #allow-the-application-through-windows-firewall }

Sous Windows, vous pouvez créer une règle d'entrée à partir de **Windows Defender Firewall avec Advanced Security**:

1. Ouvrir **Windows Defender Firewall avec sécurité avancée**.
2. Sélectionnez **Règles internes**, puis choisissez **Nouvelle règle**.
3. Sélectionnez **Port**, choisissez **TCP** et entrez le port hôte, tel que 8000.
4. Sélectionnez **Autorisez la connexion**.
5. Appliquer la règle aux profils appropriés. **Private** est habituellement le profil correct pour un réseau d'accueil fiable.
6. Donnez à la règle un nom tel que Karaoke Application, puis sélectionnez **Finish**.

??? note "You can also create the rule from an Administrator PowerShell terminal"
    ```powershell
    New-NetFirewallRule `
      -DisplayName "Karaoke Application" `
      -Direction Inbound `
      -Protocol TCP `
      -LocalPort 8000 `
      -Action Allow `
      -Profile Private
    ```

    Sur un ordinateur Windows, assurez-vous que le réseau est réglé à **Privé**.

??? note "To check or change the profile from an Administrator PowerShell terminal"

    ```powershell
    Get-NetConnectionProfile |
      Where-Object { $_.NetworkCategory -ne 'Private' } |
      ForEach-Object {
        $_
        Set-NetConnectionProfile -InterfaceIndex $_.InterfaceIndex -NetworkCategory Private -Confirm:$false
      }
    ```

### La connexion Demucs échoue { #demucs-connection-fails }

Si Demucs signale une connexion chronométrée ou aucune route vers l'hôte, vérifiez que l'hôte et le port de service Demucs sont saisis correctement.

- Dans Docker, localhost se réfère au conteneur actuel. Utilisez le nom du conteneur Demucs lorsque les deux services sont sur le même réseau Docker.
- Si Demucs fonctionne sur un autre ordinateur sur le même réseau local, utilisez l'adresse IP LAN de cet ordinateur.
- Confirmez la clé API si le service Demucs en a besoin.
- Vérifiez les journaux de service Demucs pour détecter les erreurs Demucs ou WhisperX.

Un démarrage de service réussi devrait inclure:

```text
INFO   Application startup complete.
```

You can [verify that the Demucs service is healthy](../getting-started/demucs-service.md#5-verify-application-health).

Dans certains cas, l'environnement virtuel n'est pas activé ou le mauvais environnement est utilisé lors du démarrage du service Demucs. Activez l'environnement virtuel correct avant de le démarrer.

Si Demucs s’exécute sur Internet, consultez [Exposer un service Demucs distant](../tasks/server-administration.md#expose-a-remote-demucs-service).

## yt-dlp échoue à télécharger { #yt-dlp-fails-to-download }

YouTube peut bloquer ou limiter les adresses IP utilisées par les fournisseurs VPS. Même une connexion à domicile peut être temporairement limitée ou bloquée.

Si le problème est temporaire, la solution la plus rapide est de sélectionner **Retry** sur la tâche échouée.

Si le téléchargement échoue toujours, [configurez un serveur proxy pour les téléchargements yt-dlp](../tasks/server-administration.md#use-a-proxy-server-for-downloads).

En dernier recours, téléchargez la vidéo sur votre téléphone avec [Seal](https://f-droid.org/en/packages/com.junkfood.seal/), ou utilisez yt-dlp depuis un autre ordinateur ou réseau. [Importez ensuite la vidéo](../tasks/create-ai-karaoke.md#create-karaoke-from-uploaded-files) dans l’application.

## Les lyriques ne peuvent pas être trouvés ou sont incorrectes { #lyrics-cannot-be-found-or-are-incorrect }

Vérifiez que l’application principale de karaoké est à jour. Consultez la page [Mise à niveau](../getting-started/backup-and-restore.md#upgrade).

Vous **devez** configurer les [clés API Last.fm et Musixmatch](../getting-started/docker.md#3-configure-the-environment) pour utiliser les paroles.

L'application recherche actuellement Musixmatch, LRCLIB et Netease. Si aucun de ces fournisseurs ne contient les paroles, l'application ne peut pas les trouver.

L’[option de recherche de paroles avec Google](../tasks/create-ai-karaoke.md#3-add-lyrics) cherche les paroles à partir de Artiste - Titre. Copiez les résultats et collez-les dans la zone de texte. Les paroles n’ont pas besoin d’être synchronisées : des paroles simples conviennent également.

Si l'application trouve des paroles incorrectes, Last.fm peut avoir déduit le mauvais titre de chanson ou artiste. Entrez le bon titre et artiste, puis recherchez à nouveau.

Si aucun fournisseur intégré ne fonctionne et que vous souhaitez utiliser le vôtre, suivez les [instructions relatives aux fournisseurs de paroles personnalisés](../configuration/custom-lyrics-provider.md).

N'hésitez pas à faire une demande de tirage pour ajouter votre fournisseur ou corriger les implémentations actuelles du fournisseur.

## La séparation vocale est très lente { #vocal-separation-is-very-slow }

!!! note "Demucs progress can pause near 90%"

    Si Demucs apparaît coincé à 90% pendant quelques secondes, c'est normal. Demucs ne rapporte que des progrès de séparation vocale, pas tous les travaux de configuration et de démontage, et l'application ne peut pas capturer ces progrès supplémentaires.

    La séparation vocale Demucs fonctionne au mieux avec un GPU NVIDIA compatible CUDA. Si vous disposez d’un tel GPU, vérifiez l’[état du service Demucs](../getting-started/demucs-service.md#5-verify-application-health) et confirmez que le moteur le reconnaît.

    Sur un appareil limité au CPU, [Sherpa+Spleeter](../tasks/create-ai-karaoke.md#cpu-processing) est nettement plus rapide que Demucs, au prix d’une qualité moindre. Envisagez cette option et consultez la [configuration du traitement karaoké](../configuration/karaoke-processing.md#separation-options).

## L'alignement WhisperX échoue ou prend trop de temps { #whisperx-alignment-fails-or-takes-too-long }

WhisperX utilise une grande quantité de VRAM, l'application décharge automatiquement les modèles et lance la collecte des ordures après chaque séparation vocale. Cela augmente légèrement le temps d'alignement, mais aide à empêcher WhisperX de s'accrocher.

Si WhisperX reste bloqué avec un GPU, annulez la tâche. Exécutez [Demucs GC](../configuration/tools.md#run-demucs-gc) pour libérer de la mémoire GPU, puis réessayez.

WhisperX alignment can also take longer when the lyrics are inaccurate or the wrong language is detected. If you know the language of the audio, try again and [specify the language override](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics).

??? tip "Check the detected language in the logs"

    Inspectez les journaux de service Demucs. Lors d'un mauvais alignement, il y a de bonnes chances que WhisperX détecte la mauvaise langue.

    ```text
    2026-09-13 20:34:28 - whisperx.asr - INFO -
    Detected language: ja (0.68) in first 30s of audio
    ```

    Alors que WhisperX traite une chanson, vous pouvez attendre une autre chanson. L'alignement typique prend une à deux minutes, ce qui est plus court qu'une chanson standard de trois minutes. Vous pouvez également préprocéder des pistes que vous ou vos invités aimez avant ou après la session de karaoké, lorsque la vitesse de traitement est moins critique.

    Si un ami dispose d’un ordinateur compatible CUDA, demandez-lui d’y exécuter le service Demucs ; voici les [instructions pour l’exposer sur Internet](../tasks/server-administration.md#expose-a-remote-demucs-service).

## Les paroles WhisperX sont mal synchronisées { #whisperx-lyrics-are-poorly-synchronized }

Aucun modèle n’est parfait ; de légers décalages de synchronisation sont donc prévisibles. For major issues, the language detected by WhisperX is often incorrect. If you know the language of the audio, try again and [specify the language override](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics).

Pour corriger les décalages mineurs comme importants, consultez [Résynchroniser des paroles WhisperX incorrectes](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics).

## Problèmes de lecture iOS { #ios-playback-issues }

Sur les appareils iOS, vous pouvez rencontrer des problèmes tels que la vidéo ne pas lire, le gel vidéo, le bouton de lecture ne pas répondre, ou le décalage vidéo.

Consultez [Utiliser un iPhone ou un iPad comme écran de scène](../tasks/stage-and-branding.md#use-an-iphone-or-ipad-as-a-stage-display) pour connaître les limites et solutions connues.
