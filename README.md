# Dispatchwrapparr - Super wrapper for Dispatcharr

<p align="center">
  <img src="https://github.com/user-attachments/assets/eb65168b-e24f-4e0c-b17b-7d72021d1d15" height="200" alt="Dispatchwrapparr Logo" />
</p>


## ❤️ What does dispatchwrapparr do?

✅ **Builtin DASHDRM Support** — Append `#clearkey=<clearkey>` to the end of the URL for clearkey/DRM decryption of livestreams\
✅ **High Performance** — Uses streamlink API's to offload segment downloading before passing to ffmpeg for muxing\
✅ **Highly Flexible** — Can support standard HLS, Mpeg-DASH as well as DASH-DRM, Youtube, Twitch and other livestreaming services as channels\
✅ **Proxy Support** — Full support for passing proxy servers to bypass geo restrictions\

---

## ⚙️ CLI Usage

- `-i`: Required input URL
- `-us`: Required user agent string
- `-proxy <proxy server>`: Optional proxy server. Supports http, https, socks4a and socks5h.

```dispatchwrapparr.py -i <url> -ua <user-agent> [-proxy <proxy server]```

---

## 🚀 Installation

Dispatchwrapparr is designed to work within the Dispatcharr docker container. Either copy the script into the container or add it into your configuration bind mount (recommended).

1. Create a directory inside your Dispatcharr /data bind mount/volume map called 'dispatchwrapparr'.
2. Download the python script dispatchwrapparr.py and copy it into the dispatchwrapper directory
3. Make the script executable: ```chmod +x /path/to/dispatcharr/data/dispatchwrapparr/dispatchwrapparr.py```
4. Create a new profile in Dispatcharr under 'Settings' --> 'Stream Profiles'
5. In the 'Name' field, type in 'dispatchwrapparr'
6. In the 'Command' field, type in the location of the script as it would be inside the docker container, eg. ```/data/dispatchwrapparr/dispatchwrapparr.py```
7. In the 'Parameters' field, type in ```-i {streamUrl} -ua {userAgent}```
8. Now select 'dispatchwrapparr' as your preferred profile on any particular streams!

<img width="324" height="254" alt="image" src="https://github.com/user-attachments/assets/cee7ee08-102a-4b3b-9206-46a842e0b473" />

If you wish to use a proxy server, create a separate profile:

1. In the 'Name' field, type in 'dispatchwrapparr proxy'
2. In the 'Command' field, type in the location of the script as it would be inside the docker container, eg. ```/data/dispatchwrapparr/dispatchwrapparr.py```
3. In the 'Parameters' field, type in ```-i {streamUrl} -ua {userAgent} -proxy http://your.proxy.server:3128```
4. Now select 'dispatchwrapparr proxy' on any streams that you wish to use the proxy server for.

---

## ✨ How can I play DASHDRM streams?

Easy! You'll need the clearkeys in order to play DRM protected content. There are a number of ways to acquire the keys such as scripts and browser plugins.
This script assumes that you have these keys already.

To play these streams, simply create a custom m3u8 file that places #clearkey=<clearkey> at the end of the stream URL. Below is an example that could be used for Channel 4 (UK):

```channel-4-uk.m3u8
#EXTM3U
#EXTINF:-1 group-title="United Kingdom" channel-id="Channel4London.uk" tvg-id="Channel4London.uk" tvg-logo="https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-kingdom/channel-4-uk.png", Channel 4
https://olsp.live.dash.c4assets.com/dash_iso_sp_tl/live/channel(c4)/manifest.mpd#clearkey=5ce85f1aa5771900b952f0ba58857d7a
```

More channels can be added to the same m3u8 file, and may also contain a mixture of DRM and non-DRM encrypted streams.
Simply upload your m3u8 file into Dispatcharr and select dispatchwrapparr as the profile for any streams.

## ⚖️ License
This project is licensed under the [MIT License](LICENSE).
