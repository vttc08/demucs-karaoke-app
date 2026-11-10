# Risoluzione dei problemi {#troubleshooting}

Usa questa pagina per trovare soluzioni ai problemi più comuni dell'applicazione e del servizio Demucs. Per istruzioni dettagliate, consulta la [guida per gli utenti](../tasks/for-users.md).

## Contenuto {#contents}

- [L'applicazione o Demucs non è raggiungibile](#application-or-demucs-is-not-accessible)
    - [La connessione a Demucs non riesce](#demucs-connection-fails)
- [yt-dlp non riesce a scaricare i contenuti](#yt-dlp-fails-to-download)
- [Il testo non viene trovato oppure è errato](#lyrics-cannot-be-found-or-are-incorrect)
- [La separazione delle tracce vocali è molto lenta](#vocal-separation-is-very-slow)
- [L'allineamento WhisperX non riesce o richiede troppo tempo](#whisperx-alignment-fails-or-takes-too-long)
- [I testi di WhisperX non sono sincronizzati correttamente](#whisperx-lyrics-are-poorly-synchronized)
- [Problemi di riproduzione su iOS](#ios-playback-issues)

## Applicazione o Demucs non è accessibile {#application-or-demucs-is-not-accessible}

Se non riesci a raggiungere l'applicazione principale, verifica quanto segue.

Verifica l'impostazione [HOST](../configuration/environments.md#server-and-routing). Se il server ascolta su `localhost` o `127.0.0.1`, l'applicazione è accessibile solo dal computer host. Per raggiungerla da altri dispositivi della rete locale, usa l'indirizzo IP locale dell'host. In Docker, configura l'ascolto su `0.0.0.0`, poiché il container usa una rete separata con NAT.

Controlla la mappatura delle porte Docker. In `-p 8000:8000`, il numero a sinistra indica la porta dell'host e quello a destra la porta del container. La porta dell'host può essere una qualsiasi porta libera, mentre quella del container deve corrispondere all'impostazione [PORT](../configuration/environments.md#server-and-routing).

Ad esempio, `-p 8001:8001` non funzionerà se il container è ancora configurato con `PORT=8000`. In tal caso, usa `-p 8001:8000` oppure imposta `PORT=8001` nel container.

Verifica anche che il firewall dell'host consenta il traffico in entrata sulla porta scelta.

### Consentire l'applicazione tramite Windows Firewall {#allow-the-application-through-windows-firewall}

In Windows puoi creare una regola in entrata da **Windows Defender Firewall con sicurezza avanzata**:

1. Apri **Windows Defender Firewall con sicurezza avanzata**.
2. Seleziona **Regole connessioni in entrata**, quindi **Nuova regola**.
3. Scegli **Porta**, seleziona **TCP** e inserisci la porta dell'host, ad esempio 8000.
4. Seleziona **Consenti la connessione**.
5. Per una rete domestica attendibile, in genere è adatto il profilo **Privato**.
6. Assegna un nome alla regola, ad esempio `Karaoke Application`, quindi seleziona **Fine**.

??? note "Puoi creare la regola anche da PowerShell come amministratore"
    ```powershell
    New-NetFirewallRule `
      -DisplayName "Karaoke Application" `
      -Direction Inbound `
      -Protocol TCP `
      -LocalPort 8000 `
      -Action Allow `
      -Profile Private
    ```

In Windows, verifica che il profilo di rete sia impostato su **Privato**.

??? note "Verifica o modifica il profilo da PowerShell come amministratore"

    ```powershell
    Get-NetConnectionProfile |
      Where-Object { $_.NetworkCategory -ne 'Private' } |
      ForEach-Object {
        $_
        Set-NetConnectionProfile -InterfaceIndex $_.InterfaceIndex -NetworkCategory Private -Confirm:$false
      }
    ```

### Connessione demucs non riuscita {#demucs-connection-fails}

Se Demucs segnala una connessione interrotta o l'assenza di un percorso verso l'host, verifica che l'indirizzo e la porta del servizio siano corretti.

- In Docker, localhost si riferisce al contenitore corrente. Utilizzare il nome del contenitore Demucs quando entrambi i servizi sono sulla stessa rete Docker.
- Se Demucs è in esecuzione su un altro computer della stessa rete locale, usa l'indirizzo IP locale di quel computer.
- Se il servizio Demucs richiede una chiave API, verifica che sia corretta.
- Controlla i log del servizio per individuare errori di Demucs o WhisperX.

L'avvio corretto del servizio dovrebbe includere:

```text
INFO   Application startup complete.
```

Puoi [verificare che il servizio Demucs sia sano](../getting-started/demucs-service.md#5-verify-application-health).

In alcuni casi, all'avvio del servizio Demucs non viene attivato l'ambiente virtuale oppure viene usato quello sbagliato. Attiva l'ambiente corretto prima di avviare il servizio.

Se Demucs è in esecuzione su Internet, vedere [Rendere raggiungibile un servizio Demucs remoto](../tasks/server-administration.md#expose-a-remote-demucs-service).

## yt-dlp non riesce a scaricare {#yt-dlp-fails-to-download}

yt-dlp potrebbe dover essere aggiornato quando cambia una sorgente video. Usa **Aggiorna yt-dlp** nelle impostazioni. In Docker, verifica che `YTDLP_PATH=/data/tools/yt-dlp` e che `/data` usi uno storage persistente; consulta le [variabili d'ambiente](../configuration/environments.md#downloads-and-external-tools).

YouTube può bloccare o limitare gli indirizzi IP usati dai provider VPS. Anche una connessione domestica può subire limitazioni temporanee.

Se il problema è temporaneo, la soluzione più rapida è selezionare **Riprova** nell'attività non riuscita.

Se il download continua a non riuscire, [configurare un server proxy per i download di yt-dlp](../tasks/server-administration.md#use-a-proxy-server-for-downloads).

Come ultima risorsa, scarica il video sul telefono con [Seal](https://f-droid.org/en/packages/com.junkfood.seal/) oppure usa yt-dlp da un altro computer o da un'altra rete. Poi [carica il video](../tasks/create-ai-karaoke.md#create-karaoke-from-uploaded-files) nell'applicazione.

## Il testo non può essere trovato o non è corretto {#lyrics-cannot-be-found-or-are-incorrect}

Assicurati che l'applicazione sia aggiornata. Consulta la guida all'[aggiornamento](../getting-started/backup-and-restore.md#upgrade).

Per usare la ricerca dei testi, devi configurare le [chiavi API di Last.fm e Musixmatch](../getting-started/docker.md#3-configure-the-environment).

Al momento l'applicazione cerca i testi su Musixmatch, LRCLIB e Netease. Se nessuno di questi servizi li contiene, non sarà possibile trovarli.

L'[opzione Google Lyrics](../tasks/create-ai-karaoke.md#3-add-lyrics) cerca «artista - titolo». Puoi copiare i risultati e incollare il testo nella casella dedicata. Non è necessario che sia sincronizzato: vanno bene anche i testi semplici.

Se l'applicazione trova il testo sbagliato, Last.fm potrebbe aver identificato male il titolo o l'artista. Inserisci i dati corretti e ripeti la ricerca.

Se nessuno dei servizi integrati trova il testo e vuoi usarne un altro, segui le istruzioni per [configurare un provider di testi personalizzato](../configuration/custom-lyrics-provider.md).

Puoi anche aprire una pull request per aggiungere un provider o correggere quelli esistenti.

## La separazione vocale è molto lenta {#vocal-separation-is-very-slow}

!!! note "L'avanzamento di Demucs può fermarsi per qualche istante intorno al 90%"

    Se Demucs sembra fermo al 90% per alcuni secondi, è normale. Demucs segnala solo l'avanzamento della separazione vocale, non quello delle operazioni di preparazione e chiusura; l'applicazione quindi non può mostrarlo.

La separazione vocale con Demucs è più veloce con una GPU NVIDIA compatibile con CUDA. Se ne hai una, verifica lo stato del [servizio Demucs](../getting-started/demucs-service.md#5-verify-application-health) e controlla che il backend la rilevi.

Per l'elaborazione solo con CPU, [Sherpa+Spleeter](../tasks/create-ai-karaoke.md#cpu-processing) è molto più veloce di Demucs, anche se offre una qualità inferiore. Puoi provarlo e consultare le [opzioni di separazione](../configuration/karaoke-processing.md#separation-options).

## L'allineamento WhisperX non riesce o richiede troppo tempo {#whisperx-alignment-fails-or-takes-too-long}

Poiché WhisperX usa molta VRAM, dopo ogni separazione vocale l'applicazione scarica automaticamente i modelli dalla memoria e libera le risorse. L'allineamento richiede così un po' più di tempo, ma si riduce il rischio che WhisperX si blocchi.

Se WhisperX si blocca ancora mentre usi una GPU, annulla l'attività. Esegui [Demucs GC](../configuration/tools.md#run-demucs-gc) per liberare memoria sulla GPU, quindi riprova.

L'allineamento può richiedere più tempo anche quando il testo è impreciso o viene rilevata la lingua sbagliata. Se conosci la lingua dell'audio, riprova e [specificala manualmente](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics).

??? tip "Controlla nei log la lingua rilevata"

    Controlla i log del servizio Demucs. Se l'allineamento è molto impreciso, è possibile che WhisperX abbia rilevato la lingua sbagliata.

    ```text
    2026-09-13 20:34:28 - whisperx.asr - INFO -
    Detected language: ja (0.68) in first 30s of audio
    ```

Mentre WhisperX elabora un brano, puoi aggiungerne un altro alla coda. In genere l'allineamento richiede da uno a due minuti, meno della durata di un normale brano di tre minuti. Puoi anche preparare in anticipo i brani preferiti tuoi o dei tuoi ospiti, quando la velocità di elaborazione è meno importante.

Se un tuo amico ha un computer compatibile con CUDA, può eseguire lì il servizio Demucs. Segui queste [istruzioni per renderlo accessibile da remoto](../tasks/server-administration.md#expose-a-remote-demucs-service).

## I testi di WhisperX sono mal sincronizzati {#whisperx-lyrics-are-poorly-synchronized}

Nessun modello è perfetto, quindi possono verificarsi piccoli problemi di sincronizzazione. Se il problema è grave, spesso WhisperX ha rilevato la lingua sbagliata. Se conosci la lingua dell'audio, riprova e [specificala manualmente](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics).

Per istruzioni su come correggere problemi di sincronizzazione lievi o gravi, consulta [Correggere la sincronizzazione dei testi di WhisperX](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics).

## Problemi di riproduzione iOS {#ios-playback-issues}

Sui dispositivi iOS il video potrebbe non avviarsi, bloccarsi, procedere a scatti oppure non rispondere al pulsante di riproduzione.

Vedere [Utilizzare un iPhone o un iPad come schermo del palco](../tasks/stage-and-branding.md#use-an-iphone-or-ipad-as-a-stage-display) per le limitazioni e le soluzioni alternative note.
