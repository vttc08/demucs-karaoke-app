## Stage Client
Stage client is responsible for displaying karaoke lyrics and video to the audience. 

**Desktop operating system** (Windows, Linux, MacOS) such as a laptop or desktop computer is recommended, especially for displaying to a TV or projector. Screen casting from a mobile device (AirPlay, Samsung DeX) may work but it's untested.

Android devices are supported, but may require additional stage theme configuration to best display on a small window.

iOS/iPadOS devices do not support the full functionality of the stage client, due to Apple limitations on web browsers, these devices cannot play 2 audio streams simultaneously. When using Apple devices, it's not possible to turn on the vocals, only instrumental will be played. 

In addition, browsers in some older Apple devices only support H.264 + AAC media, so [additional configuration](empty link for now) is required. 

## Guest Clients
Any device with a modern web browser will work to search, queue and control karaoke media. 

The guest must be able to reach the main application server, either local network or internet. If Wi-Fi client isolation (or Guest Network) is used, consider using a reverse proxy and enable hairpin NAT on your router. More network configuration will be covered in [deployment](deployment/index.md).

For a shared device, a tablet/laptop is suitable, consider enabling kiosk mode to prevent guests from leaving the app. 

[iPad Kiosk Mode](https://support.apple.com/en-us/111795)

[Android Kiosk App](https://github.com/RushB-fr/freekiosk)