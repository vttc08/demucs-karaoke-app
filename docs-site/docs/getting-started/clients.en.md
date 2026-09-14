## Stage Client
Stage client is responsible for displaying karaoke lyrics and video to the audience. 

**Desktop operating systems** (Windows, Linux, macOS), such as a laptop or desktop computer, are recommended, especially for displaying to a TV or projector. Screen casting from a mobile device (AirPlay, Samsung DeX) may work, but it is untested.

Android devices are supported, but may require additional stage theme configuration to best display on a small window.

iOS/iPadOS devices do not support the full functionality of the stage client, due to Apple limitations on web browsers, these devices cannot play 2 audio streams simultaneously. When using Apple devices, it's not possible to turn on the vocals, only instrumental will be played. 

In addition, browsers on some older Apple devices only support H.264 + AAC media, so see the [iPhone and iPad stage-display guidance](../tasks/stage-and-branding.md#use-an-iphone-or-ipad-as-a-stage-display).

## Guest Clients
Any device with a modern web browser will work to search, queue and control karaoke media. 

The guest must be able to reach the main application server, either local network or internet. If Wi-Fi client isolation (or Guest Network) is used, consider using a reverse proxy and enable hairpin NAT on your router. More network configuration is covered in [server administration](../tasks/server-administration.md).

For a shared device, a tablet or laptop is suitable. Consider enabling kiosk mode to prevent guests from leaving the app.

[iPad Kiosk Mode](https://support.apple.com/en-us/111795)

[Android Kiosk App](https://github.com/RushB-fr/freekiosk)
