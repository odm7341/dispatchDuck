# Dispatchwrapparr - Super wrapper for Dispatcharr

<p align="center">
  <img src="https://github.com/user-attachments/assets/eb65168b-e24f-4e0c-b17b-7d72021d1d15" height="250" alt="Dispatchwrapparr Logo" />
</p>

## 🤝 What does dispatchwrapparr do?

✅ **Builtin MPEG-DASH Clearkey/DRM Support** — Either append a `#clearkey=<clearkey>` fragment to the end of the URL or include a clearkeys json file or URL for DRM decryption\
✅ **High Performance** — Uses streamlink API's for segment dowloading which significantly improves channel start times\
✅ **Highly Flexible** — Can support standard HLS, Mpeg-DASH as well as DASH-DRM, Youtube, Twitch and other livestreaming services as channels\
✅ **Proxy Support** — Full support for passing proxy servers to bypass geo restrictions. Also support for bypassing proxy for specific URL's used in initial redirections\
✅ **Custom Header Support** — Currently supports the 'Referer' and 'Origin' headers by appending `#referer=<URL>` or `#origin=<URL>` (or both) fragments to the end of the URL\
✅ **Cookie Jar Support** — Supports loading of cookie jar txt files in Netscape/Mozilla format\
✅ **Extended Stream Type Detection** — Fallback option that checks MIME type of stream URL for streamlink plugin selection\
✅ **Automated Stream Variant Detection** — Detects streams with no video or no audio and muxes in the missing components for compatibility with most players

---

## 🚀 Installation

1. Download the latest [Dispatchwrapparr Plugin](https://github.com/jordandalley/dispatchwrapparr/releases/latest) zip file 
2. In Dispatcharr, navigate to 'Settings' > 'Plugins'
3. Click the 'Import Plugin' button and select the Dispatchwrapparr Plugin zip file you just downloaded
3. Select 'Enable Now', and then 'Enable'
4. Once the plugin is loaded, click 'Run' inside the 'Install Dispatchwrapparr' section
<img width="489" height="278" alt="image" src="https://github.com/user-attachments/assets/0b00bdd6-7ad9-428c-b2b0-66e62279e747" />

5. An alert box should come up to confirm installation
<img width="350" height="87" alt="image" src="https://github.com/user-attachments/assets/082e4a58-6d1e-4945-bcae-168692a667be" />

6. Click the refresh icon <img width="29" height="29" alt="image" src="https://github.com/user-attachments/assets/0945ad01-9af6-49bf-80e6-ff9607bdc501" /> to display all available settings

---

## ➡️ Create a Dispatchwrapparr profile

Dispatchwrapparr profiles can either be created manually under 'Settings' > 'Stream Profiles', or through the plugin interface.

1. Create a new profile using the Dispatchwrapparr Plugin, navigate to under 'Settings' > 'Plugins'
2. Enter a 'Profile Name' and fill in any other relevant details for the profile.
3. Click 'Run' next to 'Create Stream Profile'
4. Refresh your browser, then apply the profile to any particular streams that you want
5. Now select 'dispatchwrapparr' as your preferred profile on any particular streams!

## ✨ How can I play DASHDRM streams?

There are two methods for playing DASHDRM streams. Method 1 is easiest and is detailed below.

***Dispatcharr 0.9.0 / ffmpeg 8.0 / garbled/green video issue***

There is currently an issue with decrypting DASHDRM streams since the release of Dispatcharr 0.9.0.
During this release, Dispatcharr was bundled with ffmpeg 8.0 which in some circumstances returns garbled/green video content.
The solution at this stage is to download an earlier ffmpeg binary and place it into the same directory as dispatchwrapparr.py. I have also added a `-ffmpeg` argument to specify a custom ffmpeg location.
I recommend the use of [jellyfin-ffmpeg](https://github.com/jellyfin/jellyfin-ffmpeg/releases) latest `portable_linux64-gpl` release binaries.

***Method 1: Append a #clearkey=<clearkey> fragment to the stream URL***

You'll need the clearkeys in order to play DRM protected content. There are a number of ways to acquire the keys such as scripts and browser plugins.
I'll assume that you have these keys already.

To play these streams, simply create a custom m3u8 file that places the #clearkey=<clearkey> fragment at the end of the stream URL. Below is an example that could be used for Channel 4 (UK):

```channel-4-uk.m3u8
#EXTM3U
#EXTINF:-1 group-title="United Kingdom" channel-id="Channel4London.uk" tvg-id="Channel4London.uk" tvg-logo="https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-kingdom/channel-4-uk.png", Channel 4
https://olsp.live.dash.c4assets.com/dash_iso_sp_tl/live/channel(c4)/manifest.mpd#clearkey=5ce85f1aa5771900b952f0ba58857d7a
```

More channels can be added to the same m3u8 file, and may also contain a mixture of DRM and non-DRM encrypted streams.
Simply upload your m3u8 file into Dispatcharr and select dispatchwrapparr as the profile for any streams.

The `#clearkey=<clearkey>` can also be used in conjunction with other fragments. Eg: `https://olsp.live.dash.c4assets.com/dash_iso_sp_tl/live/channel(c4)/manifest.mpd#referer=https://www.channel4.com&clearkey=5ce85f1aa5771900b952f0ba58857d7a`

**Note:** If you are to use this option, be sure to remove the 'URL' item from the 'M3U Hash Key' setting. This can be found in 'Settings' -> 'Stream Settings' in Dispatcharr.

<img width="170" height="71" alt="image" src="https://github.com/user-attachments/assets/abbc4b6f-f878-44b3-906b-b0981df105e4" />

The reason why we remove the URL from the hash settings is because if the clearkey ever has to change (many channels rotate theirs regularly), then Dispatcharr won't treat the channel as new.


***Method 2: Use `-clearkeys` argument or supply a json file or URL containing URL to Clearkey mappings into the Dispatchwrapparr Plugin 'Clearkeys' field***

The `-clearkeys` argument can be supplied with a json formatted file or URL containing URL's which map to clearkeys, and performs this function in the following ways:

- Wildcards are supported. Eg. to match a clearkey to a specific URL, you can specify wildcards in the URL string. Eg. `https://olsp.live.dash.c4assets.com/*/live/channel(c4)/*.mpd`
- When a URL is supplied, it will ignore the `-proxy` directive for fetching clearkeys. It assumes that a proxy is not required for this request. This allows you to create your own clearkeys API that runs locally.
- When a file is supplied without an absolute path, it will assume that the file is in the same directory as the script. Eg. `-clearkeys clearkeys.json` would resolve to `/data/dispatchwrapparr/clearkeys.json`.
- Supports KID:KEY combinations, and comma delimited lists of clearkeys where multiple keys are required.
- If no stream URL matches a clearkey, the script will continue processing the stream as normal.

Below is an example of a `clearkeys.json` file or an expected output from an API/URL containing clearkeys. Again, below is an example that could be used for Channel 4 (UK):

```clearkeys.json
{
  "https://olsp.live.dash.c4assets.com/dash_iso_sp_tl/live/channel(c4)/manifest.mpd": "5ce85f1aa5771900b952f0ba58857d7a",
}

```

## ✨ Can I use custom headers?

Yes, however at this time only 'Referer' and 'Origin' headers are supported.

To use a 'Referer' header, simply append the `#referer=<URL>` fragment to the end of the strean URL.

For both 'Referer' and 'Origin' headers, simply append the `#referer=<URL>&origin=<URL>` fragments together, delimited by an ampersand '&'.

The `#referer=<URL>` fragment can also be used in conjunction with other fragments such as `#clearkey=<clearkey>` if needed.

If required, more custom headers could be added later. If you have a good use-case for this, please feel free to log a feature request.


## ✨ Automated Stream Variant Detection

Plex/Emby/Jellyfin expects to receive both video and audio in any streams that it plays. If a stream contains one without the other, they generally won't play.

Dispatchwrapparr will attempt to autodetect if a stream contains only audio, or only video as part of its stream variant checking.

To disable auto-detection of audio-only and video-only streams, the `-novariantcheck` flag may be used in a custom profile or the `#novariantcheck=true` url fragment.


### Audio-only streams (Eg. Streaming Radio)

If the stream is detected to have only audio, then dispatchwrapparr will mux blank video data into the stream so that it can be played.

If autodetection does not work as expected, there are two methods by which you can force the muxing of blank video into the stream.

***Method 1: Use the `-novideo` argument in a custom profile***

The `-novideo` argument can be supplied to dispatchwrapparr as a custom profile for radio station streams.

Using a streaming profile means that you could import manifests of radio streams from various sources and have them all treated as radio stations.

***Method 2: Append `#novideo=true` to the end of the stream URL***

This option works similarly to the other fragment options. In an m3u8 file, simply append a `#novideo=true` fragment to the end of the stream URL, and dispatchwrapparr will treat it as a radio station.

Below is an example of a custom m3u8 manifest with Channel X from New Zealand, and the `#novideo=true` fragment appended.

```channel-x.m3u8
#EXTM3U
#EXTINF:-1 tvg-id="Radio.Channel.X" group-title="Radio" tvg-logo="https://images.mediaworks.nz/rova/Content/apps/images/ChannelX_600x600.png",Channel X
https://mediaworks.streamguys1.com/chx_net/playlist.m3u8#novideo=true
```

### Video-only streams (Eg. Live Cameras)

If the stream is detected to have only video, then dispatchwrapparr will mux silent audio into the stream so that it can be played.

If autodetection does not work as expected, there are two methods by which you can force the muxing of silent audio into the stream.

***Method 1: Append `#noaudio=true` fragment to the stream URL***

In an m3u8 file, simply append a `#noaudio=true` fragment to the end of the stream URL, and dispatchwrapparr will generate dummy audio for the stream.

Below is an example of a custom m3u8 manifest with the SEN 4K Livestream from the International Space Station with multiple fragments including `#noaudio=true` appended.

```sen-iss.m3u8
#EXTM3U
#EXTINF:-1 tvg-id="ISS.SEN.4K" group-title="Miscellaneous" tvg-logo="https://about.sen.com/wp-content/uploads/2024/07/Sen_Logo_XL_RGB_White_Bitmap.png",SEN ISS (Raw 4K)
https://spacetv.sen.com/out/v1/058d27c98eb543c987d75d60085b61c7/index/index.m3u8#referer=https://www.sen.com/&origin=https://www.sen.com/&noaudio=true
```

***Method 2: Create a custom streaming profile in Dispatcharr for Video-Only Streams***

The `-noaudio` argument can be supplied to dispatchwrapparr as a custom profile for video-only streams.

Note: Using the novideo and noaudio arguments either as a fragment or a cli argument will disable the stream variant detection.

---

## ⚙️ Advanced CLI Usage

- `-i`: Required input URL
- `-ua`: Required user agent string
- `-proxy <proxy server>`: Optional: Configure a proxy server. Supports http, https only.
- `-proxybypass <comma-delimited hostnames>`: Optional. A comma delimited list of hostnames to bypass. Eg. '.local,192.168.0.44:90'. Do not use "*", this is unsupported. Wilcards match with '.'
- `-clearkeys <clearkey file or url>`: Optional: Supply a json file or URL containing json URL to clearkey mappings.
- `-cookies <cookie file>`: Optional: Supply a cookies txt file in Mozilla/Netscape format for us with streams.
- `-stream <stream selection>`: Optional: Supply a streamlink stream selection, eg. "worst" "1080p_alt" etc. Alternatively, use the `#stream=<selection>` URL fragment.
- `-ffmpeg <ffmpeg location>`: Optional: Specify the location of an ffmpeg binary for use in stream muxing instead of auto detecting ffmpeg binaries in PATH or in the same directory as dispatchwrapparr.
- `-novariantcheck`: Optional: Skips checks for streams containing video or audio only. Will not force muxing of missing audio or video. Cannot be used with -novideo or -noaudio arguments.
- `-novideo`: Optional: Designates the stream as containing no video. Forces muxing of blank video into the stream if it is not detected during variant checking automatically.
- `-noaudio`: Optional: Designates the stream as containing no audio. Forces muxing of silent audio into the stream if it is not detected during variant checking automatically.
- `-loglevel <loglevel>`: Optional: to change the default log level of "INFO". Supported options: "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", and "NOTSET".
- `-subtitles`: Optional to enable muxing of subtitles. Disabled by default. NOTE: Subtitle support in streamlink is limited at best. May not work as intended.

Example: `dispatchwrapparr.py -i {streamUrl} -ua {userAgent} [-proxy 'http://your.proxy.server:3128' -proxybypass '192.168.0.55,.somesite.com' -clearkeys 'clearkeys.json' -loglevel 'INFO' -subtitles]`

---

## ❤️ Shoutouts

This script was made possible thanks to many wonderful python libraries and open source projects.

- [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr) development community for making such an awesome stream manager!
- [SergeantPanda](https://github.com/SergeantPanda) for support and guidance on the Dispatcharr discord
- [OkinawaBoss](https://github.com/OkinawaBoss) for creating the Dispatcharr plugin system and providing example code
- [Streamlink](https://streamlink.github.io/) for their awesome API and stream handling capability
- [titus-au](https://github.com/titus-au/streamlink-plugin-dashdrm) who laid a lot of the groundwork for managing DASHDRM streams in streamlink!
- [matthuisman](https://github.com/matthuisman) this guy is a local streaming legend in New Zealand. His code and work with streams has taught me heaps!

## ⚖️ License
This project is licensed under the [MIT License](LICENSE).
