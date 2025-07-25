# Dispatchwrapparr - Super wrapper for Dispatcharr

<p align="center">
  <img src="https://github.com/user-attachments/assets/eb65168b-e24f-4e0c-b17b-7d72021d1d15" height="250" alt="Dispatchwrapparr Logo" />
</p>


## 🤝 What does dispatchwrapparr do?

✅ **Builtin MPEG-DASH Clearkey/DRM Support** — Append `#clearkey=<clearkey>` to the end of the URL for clearkey/DRM decryption of livestreams\
✅ **High Performance** — Uses streamlink API's to offload segment downloading before passing to ffmpeg for muxing\
✅ **Highly Flexible** — Can support standard HLS, Mpeg-DASH as well as DASH-DRM, Youtube, Twitch and other livestreaming services as channels\
✅ **Proxy Support** — Full support for passing proxy servers to bypass geo restrictions\
✅ **Extended Stream Type Detection** — Fallback option that checks MIME type of stream URL for streamlink plugin selection

---

## ⚙️ CLI Usage

- `-i`: Required input URL
- `-us`: Required user agent string
- `-proxy <proxy server>`: Optional proxy server. Supports http, https, socks4a and socks5h.
- `-subtitles`: Optional to enable muxing of subtitles. Disabled by default.

Example: `dispatchwrapparr.py -i <url> -ua <user-agent> [-proxy <proxy server> -subtitles]`

---

## 🚀 Script Installation

1. This command will install Dispatchwrapparr into your [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr) docker container.

```bash
docker exec -it dispatcharr bash -c \
"mkdir -p /data/dispatchwrapparr && \
curl -s 'https://raw.githubusercontent.com/jordandalley/dispatchwrapparr/refs/heads/main/dispatchwrapparr.py' -o '/data/dispatchwrapparr/dispatchwrapparr.py' && \
chmod +x '/data/dispatchwrapparr/dispatchwrapparr.py'"
```

## ➡️ Create a Dispatchwrapparr profile

1. Create a new profile in Dispatcharr under 'Settings' > 'Stream Profiles'
2. In the 'Name' field, type in 'dispatchwrapparr'
3. In the 'Command' field, type in the location of the script as it would be inside the docker container, eg. `/data/dispatchwrapparr/dispatchwrapparr.py`
4. In the 'Parameters' field, type in `-i {streamUrl} -ua {userAgent}`
5. Now select 'dispatchwrapparr' as your preferred profile on any particular streams!

<img width="324" height="254" alt="image" src="https://github.com/user-attachments/assets/cee7ee08-102a-4b3b-9206-46a842e0b473" />

If you wish to use a proxy server, create a separate profile:

6. In the 'Name' field, type in 'dispatchwrapparr proxy'
7. In the 'Command' field, type in the location of the script as it would be inside the docker container, eg. `/data/dispatchwrapparr/dispatchwrapparr.py`
8. In the 'Parameters' field, type in `-i {streamUrl} -ua {userAgent} -proxy http://your.proxy.server:3128`
9. Now select 'dispatchwrapparr proxy' on any streams that you wish to use the proxy server for.

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

## ❤️ Shoutouts

This script was made possible thanks to many wonderful python libraries and open source projects.

- [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr) development community for making such an awesome stream manager!
- [Streamlink](https://streamlink.github.io/) for their awesome API and stream handling capability
- [titus-au](https://github.com/titus-au/streamlink-plugin-dashdrm) who laid a lot of the groundwork for managing DASHDRM streams in streamlink!

## ⚖️ License
This project is licensed under the [MIT License](LICENSE).
