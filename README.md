# Dispatchwrapparr - Super wrapper for Dispatcharr

<p align="center">
  <img src="https://github.com/user-attachments/assets/eb65168b-e24f-4e0c-b17b-7d72021d1d15" height="250" alt="Dispatchwrapparr Logo" />
</p>


## 🤝 What does dispatchwrapparr do?

✅ **Builtin MPEG-DASH Clearkey/DRM Support** — Either append `#clearkey=<clearkey>` to the end of the URL or include a clearkeys json file or URL for DRM decryption\
✅ **High Performance** — Uses streamlink API's to offload segment downloading before passing to ffmpeg for muxing\
✅ **Highly Flexible** — Can support standard HLS, Mpeg-DASH as well as DASH-DRM, Youtube, Twitch and other livestreaming services as channels\
✅ **Proxy Support** — Full support for passing proxy servers to bypass geo restrictions\
✅ **Extended Stream Type Detection** — Fallback option that checks MIME type of stream URL for streamlink plugin selection

---

## ⚙️ CLI Usage

- `-i`: Required input URL
- `-us`: Required user agent string
- `-proxy <proxy server>`: Optional: Configure a proxy server. Supports http, https, socks4a and socks5h.
- `-clearkeys <clearkey file or url>`: Optional: Supply a json file or URL containing json URL to clearkey mappings
- `-loglevel <loglevel>`: Optional to change the default log level of "INFO". Supported options: "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", and "NOTSET".
- `-subtitles`: Optional to enable muxing of subtitles. Disabled by default. NOTE: Subtitle support in streamlink is limited at best. May not work as intended.

Example: `dispatchwrapparr.py -i <url> -ua <user-agent> [-proxy <proxy server> -clearkeys <clearkey file or url> -loglevel <log level> -subtitles]`

---

## 🚀 Script Installation & Update

1. This command will install or update Dispatchwrapparr to the latest version into your [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr) docker container.

```bash
docker exec -it dispatcharr bash -c
  "mkdir -p /data/dispatchwrapparr && \
  curl -sSL \
    'https://raw.githubusercontent.com/jordandalley/dispatchwrapparr/refs/heads/main/dispatchwrapparr.py' \
    -o '/data/dispatchwrapparr/dispatchwrapparr.py' && \
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

Easy! There are two methods, the first of which is the most simple for starting out.

1. Append #clearkey=<clearkey> to the URL of the stream in an m3u8 file or manual addition into Dispatcharr. Or,

You'll need the clearkeys in order to play DRM protected content. There are a number of ways to acquire the keys such as scripts and browser plugins.
This script assumes that you have these keys already.

To play these streams, simply create a custom m3u8 file that places #clearkey=<clearkey> at the end of the stream URL. Below is an example that could be used for Channel 4 (UK):

```channel-4-uk.m3u8
#EXTM3U
#EXTINF:-1 group-title="United Kingdom" channel-id="Channel4London.uk" tvg-id="Channel4London.uk" tvg-logo="https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-kingdom/channel-4-uk.png", Channel 4
https://olsp.live.dash.c4assets.com/dash_iso_sp_tl/live/channel(c4)/manifest.mpd#clearkey=5ce85f1aa5771900b952f0ba58857d7a
```

More channels can be added to the same m3u8 file, and may also contain a mixture of DRM and non-DRM encrypted streams.
Simply upload your m3u8 file into Dispatcharr and select dispatchwrapparr as the profile for any streams.

2. The second method is to supply a json file or URL which contains mappings between stream URL's and a clearkeys by using the `-clearkeys` method.

The `-clearkeys` directive behaves in the following way:

- Wildcards are supported. Eg. to match a clearkey to a specific URL, you can specify wildcards in the URL string. Eg. `https://olsp.live.dash.c4assets.com/dash_iso_sp_tl/live/channel(c4)/*.mpd`
- When a URL is supplied, it will ignore the `-proxy` directive for fetching clearkeys. It assumes that a proxy is not required for this request. This means you could create your own clearkeys API that runs locally.
- When a file is supplied without an absolute path, it will assume that the file is in the same directory as the script. Eg. `-clearkeys clearkeys.json` would resolve to `/data/dispatchwrapparr/clearkeys.json`.

Example of `clearkeys.json` file or output from an API/URL containing clearkeys. Again, below is an example that could be used for Channel 4 (UK):

```clearkeys.json
{
  "https://olsp.live.dash.c4assets.com/dash_iso_sp_tl/live/channel(c4)/manifest.mpd": "5ce85f1aa5771900b952f0ba58857d7a",
}

```

## ❤️ Shoutouts

This script was made possible thanks to many wonderful python libraries and open source projects.

- [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr) development community for making such an awesome stream manager!
- [Streamlink](https://streamlink.github.io/) for their awesome API and stream handling capability
- [titus-au](https://github.com/titus-au/streamlink-plugin-dashdrm) who laid a lot of the groundwork for managing DASHDRM streams in streamlink!

## ⚖️ License
This project is licensed under the [MIT License](LICENSE).
