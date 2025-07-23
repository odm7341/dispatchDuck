#!/usr/bin/env python3

"""

Dispatchwrapparr - Version 0.2 Alpha: A wrapper for Dispatcharr that supports the following:

  - M3U8/DASH-MPD best stream selection, segment download handling and piping to ffmpeg
  - DASH-MPD DRM clearkey support
  - HTTP Proxy Support
  - Support for Youtube Livestreams and many others

Usage: dispatchwrapper.py -i <URL> -ua <User Agent String>
Optional: -proxy <Proxy Server>

DRM/Clearkey Encrypted streams must be fed with #clearkey=<clearkey> at the end of the
url string, or supply dispatcharr a custom m3u8 file formatted like the following Channel 4 UK example:

---------------------------------------------------- channel-4.m3u8 ------------------------------------------------------
#EXTM3U
#EXTINF:-1 group-title="United Kingdom",Channel 4
https://olsp.live.dash.c4assets.com/dash_iso_sp_tl/live/channel(c4)/manifest.mpd#clearkey=5ce85f1aa5771900b952f0ba58857d7a
-------------------------------------------------------------------------------------------------------------------------

"""

from __future__ import annotations

import re
import sys
import itertools
import logging
import base64
import argparse
import requests
import socket
import ipaddress
from urllib.parse import urlparse

from collections import defaultdict
from contextlib import suppress
from typing import List, Self, Tuple, Optional
from datetime import timedelta

from streamlink import Streamlink
from streamlink.exceptions import PluginError, FatalPluginError, NoPluginError
from streamlink.plugin import Plugin, pluginmatcher, pluginargument
from streamlink.plugin.plugin import HIGH_PRIORITY, parse_params, stream_weight
from streamlink.stream.dash import DASHStream, DASHStreamWorker, DASHStreamWriter, DASHStreamReader
from streamlink.stream.dash.manifest import MPD, Representation
from streamlink.stream.ffmpegmux import FFMPEGMuxer
from streamlink.stream import HTTPStream, HLSStream, DASHStream
from streamlink.utils.url import update_scheme
from streamlink.session import Streamlink
from streamlink.utils.l10n import Language
from streamlink.utils.times import now

"""
Begin DASH DRM Plugin
Code adapted from streamlink-plugin-dashdrm by titus-au: https://github.com/titus-au/streamlink-plugin-dashdrm
A special thanks!
"""

log = logging.getLogger(__name__)

DASHDRM_OPTIONS = [
    "decryption-key",
    "presentation-delay",
    "use-subtitles",
]

@pluginmatcher(
    priority=HIGH_PRIORITY,
    pattern=re.compile(r"dashdrm://(?P<url>\S+)(?:\s(?P<params>.+))?$"),
)

@pluginargument(
    "decryption-key",
    type="comma_list",
    help="Decryption key to be passed to ffmpeg."
)

@pluginargument(
    "presentation-delay",
    help="Override presentation delay value (in seconds). Similar to"
    " --hls-live-edge."
)

@pluginargument(
    "use-subtitles",
    action="store_true",
    help="Experiment with subtitles."
)

class MPEGDASHDRM(Plugin):
    @classmethod
    def stream_weight(cls, stream):
        match = re.match(r"^(?:(.*)\+)?(?:a(\d+)k)$", stream)
        if match and match.group(1) and match.group(2):
            weight, group = stream_weight(match.group(1))
            weight += int(match.group(2))
            return weight, group
        elif match and match.group(2):
            return stream_weight(f"{match.group(2)}k")
        else:
            return stream_weight(stream)

    def _get_streams(self):
        data = self.match.groupdict()
        url = update_scheme("https://", data.get("url"), force=False)
        params = parse_params(data.get("params"))
        log.debug(f"URL={url}; params={params}")

        # process and store plugin options before passing streams back
        for option in DASHDRM_OPTIONS:
            if option == 'decryption-key':
                self.session.options[option] = self._process_keys()
            else:
                self.session.options[option] = self.get_option(option)

        return DASHStreamDRM.parse_manifest(self.session,
                                            url,
                                            **params)

    def _process_keys(self):
        keys = self.get_option('decryption-key')
        # if a colon separated key is given, assume its kid:key and take the
        # last component after the colon
        return_keys = []
        for k in keys:
            key = k.split(':')
            key_len = len(key[-1])
            log.debug('Decryption Key %s has %s digits', key[-1], key_len)
            if key_len in (21, 22, 23, 24):
                # key len of 21-24 may mean a base64 key was provided, so we
                # try and decode it
                log.debug("Decryption key length is too short to be hex and looks like it might be base64, so we'll try and decode it..")
                b64_string = key[-1]
                padding = 4 - (len(b64_string) % 4)
                b64_string = b64_string + ("=" * padding)
                b64_key = base64.urlsafe_b64decode(b64_string).hex()
                if b64_key:
                    key = [b64_key]
                    key_len = len(b64_key)
                    log.debug('Decryption Key (post base64 decode) is %s and has %s digits', key[-1], key_len)
            if key_len == 32:
                # sanity check that it's a valid hex string
                try:
                    int(key[-1], 16)
                except ValueError as err:
                    raise FatalPluginError(f"Expecting 128bit key in 32 hex digits, but the key contains invalid hex.")
            elif key_len != 32:
                raise FatalPluginError(f"Expecting 128bit key in 32 hex digits.")
            return_keys.append(key[-1])
        return return_keys


class FFMPEGMuxerDRM(FFMPEGMuxer):
    '''
    Inherit and extend the FFMPEGMuxer class to pass decryption keys
    to ffmpeg

    We build a list of keys to use based on the value of command line option
    --dashdrm-decryption-keys. If only 1 key is given, it's used for
    all streams. If more than 1 key is given, the first key is used for
    video, and the remaining keys used for remaining streams. If the number
    of keys given is less than the number of streams, keys are looped
    starting from the first key after the video key. This will basically
    mean if you have a key for video, and a key for the rest of the streams
    you just need to specify 2 keys, but alternatively you can provide a
    different key for every single stream if needed
    '''

    @classmethod
    def _get_keys(cls, session):
        keys=[]
        if session.options.get("decryption-key"):
            keys = session.options.get("decryption-key")
            # If only 1 key is given, then we use that also for all remaining
            # streams
            if len(keys) == 1:
                keys.extend(keys)
        log.debug('Decryption Keys %s', keys)
        return keys

    def __init__(self, session, *streams, **options):
        super().__init__(session, *streams, **options)
        # if a decryption key is set, we rebuild the ffmpeg command list
        # to include the key before specifying the input stream
        keys = self._get_keys(session)
        key = 0
        subtitles = self.session.options.get("use-subtitles")
        # Build new ffmpeg command list
        old_cmd = self._cmd.copy()
        self._cmd = []
        while len(old_cmd) > 0:
            cmd = old_cmd.pop(0)
            if keys and cmd == "-i":
                _ = old_cmd.pop(0)
                self._cmd.extend(["-re"])
                self._cmd.extend(["-readrate_initial_burst", "10"])
                self._cmd.extend(["-decryption_key", keys[key]])
                self._cmd.extend(["-copyts"])
                key += 1
                # If we had more streams than keys, start with the first
                # audio key again
                if key == len(keys):
                    key = 1
                self._cmd.extend([cmd, _])
                # self._cmd.extend(['-thread_queue_size', '4096'])
            elif subtitles and cmd == "-c:a":
                _ = old_cmd.pop(0)
                self._cmd.extend([cmd, _])
                self._cmd.extend(["-c:s", "copy"])
            else:
                self._cmd.append(cmd)
        if self._cmd and (self._cmd[-1].startswith("pipe:") or not self._cmd[-1].startswith("-")):
            final_output = self._cmd.pop()
            self._cmd.extend(["-mpegts_copyts", "1"])
            self._cmd.append(final_output)
        log.debug("Updated ffmpeg command %s", self._cmd)

class DASHStreamWriterDRM(DASHStreamWriter):
    reader: DASHStreamReaderDRM
    stream: DASHStreamDRM


class DASHStreamWorkerDRM(DASHStreamWorker):
    reader: DASHStreamReaderDRM
    writer: DASHStreamWriterDRM
    stream: DASHStreamDRM

    def next_period_available(self):
        '''
        Check whether there are any more periods in the overall list of periods
        beyond the current period id. If so, return the index for the next period
        otherwise return 0
        '''
        period_id = self.reader.ident[0]
        current_period_ids = [ p.id for p in self.mpd.periods ]
        current_period_idx = current_period_ids.index(period_id)

        log.debug("Current playing period: %s", current_period_idx + 1)
        log.debug("Number of periods: %s", len(current_period_ids))

        if len(current_period_ids) > current_period_idx + 1:
            return current_period_idx + 1
        return 0

    def check_new_rep(self):
        '''
        Check if new representation is available, if so find the matching stream
        name and return with the new rep's stream object
        '''
        new_rep = None
        log.debug("Checking for new representations")
        next_period = self.next_period_available()
        if next_period:
            # reparse manifest to find the next stream
            reloaded_streams = DASHStreamDRM.parse_manifest(self.session,
                                                        self.mpd.url,
                                                        next_period)
            reload_stream = reloaded_streams[self.stream.stream_name]
            if self.reader.mime_type == "video/mp4":
                new_rep = reload_stream.video_representation
                log.debug("New video representation found!")
            elif self.reader.mime_type == "audio/mp4":
                new_rep = reload_stream.audio_representation
                log.debug("New audio representation found!")
            else:
                log.debug("No new representation found!")
        return new_rep

    def iter_segments(self):
        '''
        This is copy of iter_segments, but with DRM checks disabled,
        and slight change to limit max amount of time to wait before
        looking for segments
        '''
        init = True
        back_off_factor = 1
        new_rep = None
        yield_count = -1
        while not self.closed:
            # find the representation by ID
            representation = self.mpd.get_representation(self.reader.ident)

            # check if a new representation is available
            if not new_rep:
                new_rep = self.check_new_rep()

            if self.mpd.type == "static":
                refresh_wait = 5
            else:
                refresh_wait = (
                    max(
                        self.mpd.minimumUpdatePeriod.total_seconds(),
                        # dont take the whole rep duration as wait time
                        # as some mpd will set a large number. we then
                        # end up staying in the sleeper loop too long
                        # and ffmpeg will timeout
                        min(representation.period.duration.total_seconds(),5)
                        if representation else 0,
                    )
                    or 5
                )

            if new_rep and not yield_count:
                # New rep available and no yield so we swap to the new one
                self.reader.ident = new_rep.ident
                representation = new_rep
                new_rep = None
            elif new_rep and yield_count:
                # New rep available but we had yield so we dont swap yet.
                # Set refresh to be very low since we know we actually have
                # new content in the from of new_rep
                refresh_wait = 1

            with self.sleeper(refresh_wait * back_off_factor):
                if not representation:
                    continue

                iter_segments = representation.segments(
                    init=init,
                    # sync initial timeline generation between audio and video threads
                    timestamp=self.reader.timestamp if init else None,
                )
                yield_count = 0
                for segment in iter_segments:
                    if self.closed:
                        break
                    yield_count += 1
                    yield segment

                # close worker if type is not dynamic (all segments were put into writer queue)
                if self.mpd.type != "dynamic":
                    self.close()
                    return

                if not self.reload():
                    back_off_factor = max(back_off_factor * 1.3, 10.0)
                else:
                    back_off_factor = 1

                init = False


class DASHStreamReaderDRM(DASHStreamReader):
    __worker__ = DASHStreamWorkerDRM
    __writer__ = DASHStreamWriterDRM

    worker: DASHStreamWorkerDRM
    writer: DASHStreamWriterDRM
    stream: DASHStreamDRM


class DASHStreamReaderSUB(DASHStreamReader):
    __worker__ = DASHStreamWorkerDRM
    __writer__ = DASHStreamWriterDRM

    worker: DASHStreamWorkerDRM
    writer: DASHStreamWriterDRM
    stream: DASHStreamDRM

    def read(self, size: int) -> bytes:
        _ = self.buffer.read(
            size,
            block=self.writer.is_alive(),
            timeout=self.timeout,
        )
        log.debug("Subtitle stream segment: %s", _)
        return _

class DASHStreamDRM(DASHStream):
    """
    Implementation of the "Dynamic Adaptive Streaming over HTTP" protocol (MPEG-DASH)
    """
    def __init__(
        self,
        session: Streamlink,
        mpd: MPD,
        video_representation: Representation | None = None,
        audio_representations: List[Representation] | None = None,
        subtitles_representations: List[Representation] | None = None,
        **kwargs,
    ):
        super().__init__(
            session,
            mpd,
            video_representation,
            audio_representations[0] if audio_representations[0] else None,
            **kwargs,
        )
        self.audio_representations = audio_representations
        self.subtitles_representations = subtitles_representations

    __shortname__ = "dashdrm"

    @classmethod
    def parse_manifest(
        cls,
        session: Streamlink,
        url_or_manifest: str,
        period: int | str = 0,
        with_video_only: bool = False,
        with_audio_only: bool = False,
        **kwargs,
    ) -> dict[str, DASHStreamDRM]:
        """
        Parse a DASH manifest file and return its streams.

        :param session: Streamlink session instance
        :param url_or_manifest: URL of the manifest file or an XML manifest string
        :param period: Which MPD period to use (index number (int) or ``id`` attribute (str)) for finding representations
        :param with_video_only: Also return video-only streams, otherwise only return muxed streams
        :param with_audio_only: Also return audio-only streams, otherwise only return muxed streams
        :param kwargs: Additional keyword arguments passed to :meth:`requests.Session.request`
        """

        manifest, mpd_params = cls.fetch_manifest(session, url_or_manifest, **kwargs)

        try:
            mpd = cls.parse_mpd(manifest, mpd_params)
        except Exception as err:
            raise PluginError(f"Failed to parse MPD manifest: {err}") from err

        if session.options.get("presentation-delay"):
            presentation_delay = session.options.get("presentation-delay")
            mpd.suggestedPresentationDelay = timedelta(
                                                seconds=int(presentation_delay)
                                                )

        source = mpd_params.get("url", "MPD manifest")
        video: list[Representation | None] = [None] if with_audio_only else []
        audio: list[Representation | None] = [None] if with_video_only else []
        subtitles: list[Representation | None] = [None] if with_audio_only else []

        available_periods = [f"{idx}{f' (id={p.id!r})' if p.id is not None else ''}" for idx, p in enumerate(mpd.periods)]
        log.debug(f"Available DASH periods: {', '.join(available_periods)}")

        try:
            if isinstance(period, int):
                period_selection = mpd.periods[period]
            else:
                period_selection = mpd.periods_map[period]
        except LookupError:
            raise PluginError(
                f"DASH period {period!r} not found. Select a valid period by index or by id attribute value.",
            ) from None

        # Search for suitable video and audio representations
        for aset in period_selection.adaptationSets:
            if aset.contentProtections:
                if not session.options.get("decryption-key"):
                    raise PluginError(f"{source} is protected by DRM but no key given")
                else:
                    log.debug(f"{source} is protected by DRM")
            for rep in aset.representations:
                if rep.contentProtections:
                    if not session.options.get("decryption-key"):
                        raise PluginError(f"{source} is protected by DRM but no key given")
                    else:
                        log.debug(f"{source} is protected by DRM")
                if rep.mimeType.startswith("video"):
                    video.append(rep)
                elif rep.mimeType.startswith("audio"):  # pragma: no branch
                    audio.append(rep)
                elif (session.options.get("use-subtitles") and
                        rep.mimeType.startswith("application")):
                    subtitles.append(rep)

        if not video:
            video.append(None)
        if not audio:
            audio.append(None)
        if not subtitles:
            subtitles.append(None)

        locale = session.localization
        locale_lang = locale.language
        lang = None
        available_languages = set()

        # if the locale is explicitly set, prefer that language over others
        for aud in audio:
            if aud and aud.lang:
                available_languages.add(aud.lang)
                with suppress(LookupError):
                    if locale.explicit and aud.lang and Language.get(aud.lang) == locale_lang:
                        lang = aud.lang

        if not lang:
            # filter by the first language that appears
            lang = audio[0].lang if audio[0] else None

        log.debug(
            f"Available languages for DASH audio streams: {', '.join(available_languages) or 'NONE'} (using: {lang or 'n/a'})",
        )

        # if the language is given by the stream, filter out other languages that do not match
        if len(available_languages) > 1:
            audio = [a for a in audio if a and (a.lang is None or a.lang == lang)]

        ret = []
        for vid, aud in itertools.product(video, audio):
            if not vid and not aud:
                continue

            stream = DASHStreamDRM(session, mpd, vid, audio, subtitles, **kwargs)
            stream_name = []

            if vid:
                stream_name.append(f"{vid.height or vid.bandwidth_rounded:0.0f}{'p' if vid.height else 'k'}")
            #if aud and len(audio) > 1:
            #    stream_name.append(f"a{aud.bandwidth:0.0f}k")
            ret.append(("+".join(stream_name), stream))

        # rename duplicate streams
        dict_value_list = defaultdict(list)
        for k, v in ret:
            dict_value_list[k].append(v)

        def sortby_bandwidth(dash_stream: DASHStreamDRM) -> float:
            if dash_stream.video_representation:
                return dash_stream.video_representation.bandwidth
            #if dash_stream.audio_representation:
            #    return dash_stream.audio_representation.bandwidth
            return 0  # pragma: no cover

        ret_new = {}
        for q in dict_value_list:
            items = dict_value_list[q]

            with suppress(AttributeError):
                items = sorted(items, key=sortby_bandwidth, reverse=True)

            for n in range(len(items)):
                if n == 0:
                    ret_new[q] = items[n]
                elif n == 1:
                    ret_new[f"{q}_alt"] = items[n]
                else:
                    ret_new[f"{q}_alt{n}"] = items[n]

        # add stream_name to the returned streams so we can find it again
        for stream_name in ret_new:
            ret_new[stream_name].stream_name = stream_name

        return ret_new

    def open(self):
        video, audio, audio1 = None, None, None
        rep_video = self.video_representation
        rep_audios = self.audio_representations
        rep_subtitles = self.subtitles_representations

        timestamp = now()

        fds = []

        maps = ["0:v?", "0:a?"]
        metadata = {}

        if rep_video:
            video = DASHStreamReaderDRM(self, rep_video, timestamp)
            log.debug(f"Opening DASH reader for: {rep_video.ident!r} - {rep_video.mimeType}")
            video.open()
            fds.append(video)

        #if rep_audio:
        #    audio = DASHStreamReaderDRM(self, rep_audio, timestamp)
        #    log.debug(f"Opening DASH reader for: {rep_audio.ident!r} - {rep_audio.mimeType}")

        next_map = 1
        if rep_audios:
            for i, rep_audio in enumerate(rep_audios):
                audio = DASHStreamReaderDRM(self, rep_audio, timestamp)
                if not audio1:
                    audio1 = audio
                log.debug(f"Opening DASH reader for: {rep_audio.ident!r} - {rep_audio.mimeType}")
                audio.open()
                fds.append(audio)
                metadata["s:a:{0}".format(i)] = ["language={0}".format(rep_audio.lang), "title=\"{0}\"".format(rep_audio.lang)]
            maps.extend(f"{i}:a" for i in range(next_map, next_map + len(rep_audios)))
            next_map = len(rep_audios) + 1

        # only do subtitles if we have video
        if rep_subtitles and rep_subtitles[0] and rep_video:
            for _, rep_subtitle in enumerate(rep_subtitles):
                #if not rep_subtitle:
                    #break
                subtitle = DASHStreamReaderSUB(self, rep_subtitle, timestamp)
                log.debug(f"Opening DASH reader for: {rep_subtitle.ident!r} - {rep_subtitle.mimeType}")
                subtitle.open()
                fds.append(subtitle)
                metadata["s:s:{0}".format(_)] = ["language={0}".format(rep_subtitle.lang), "title=\"{0}\"".format(rep_subtitle.lang)]
            maps.extend(f"{_}:s" for _ in range(next_map, next_map + len(rep_subtitles)))

        if video and audio and FFMPEGMuxerDRM.is_usable(self.session):
            return FFMPEGMuxerDRM(self.session, *fds, copyts=True, maps=maps, metadata=metadata).open()
        elif video:
            return video
        elif audio:
            return audio1

"""
End of DASHDRM Plugin Section
Beginning of Dispatchwrappar Section
"""

def parse_args():
    # Initial wrapper arguments
    parser = argparse.ArgumentParser(description="Dispatchwrappar: A wrapper for Dispatcharr")
    parser.add_argument("-i", required=True, help="Input URL")
    parser.add_argument("-ua", required=True, help="User-Agent string")
    parser.add_argument("-proxy", help="Optional HTTP proxy (e.g. http://127.0.0.1:8888)")
    return parser.parse_args()

def check_clearkey(raw_url: str):
    """
    Parses the input URL. If it contains '#clearkey=', splits it into the stream URL and the ClearKey string.

    The ClearKey string may be a single key or a comma-delimited list of keys (optionally including KIDs).

    Args:
        raw_url (str): The raw URL from the -i argument.

    Returns:
        tuple: (stream_url, clearkey) where clearkey is the extracted string or None.
    """
    if '#clearkey=' in raw_url:
        stream_url, clearkey = raw_url.split('#clearkey=', 1)
        return stream_url, clearkey
    return raw_url, None



def detect_stream_type(session, url, user_agent=None, proxy=None):
    try:
        return session.streams(url)
    except NoPluginError:
        print("[WARN] No plugin found for URL. Attempting fallback based on MIME type...")

        headers = {
            "User-Agent": user_agent or "Mozilla/5.0",
            "Range": "bytes=0-1023"
        }

        proxies = {
            "http": proxy,
            "https": proxy
        } if proxy else None

        try:
            response = requests.get(
                url,
                headers=headers,
                proxies=proxies,
                stream=True,
                timeout=5
            )
            content_type = response.headers.get("Content-Type", "").lower()
            print(f"[INFO] Detected Content-Type: {content_type}")
        except Exception as e:
            print(f"[ERROR] Could not detect stream type: {e}")
            raise

        if "vnd.apple.mpegurl" in content_type or "x-mpegurl" in content_type:
            return HLSStream.parse_variant_playlist(session, url)
        elif "dash+xml" in content_type:
            return DASHStream.parse_manifest(session, url)
        elif "video/mp2t" in content_type or "application/octet-stream" in content_type:
            return {"live": HTTPStream(session, url)}
        else:
            print("[ERROR] Unrecognized Content-Type for fallback")
            raise

    except PluginError as e:
        print(f"[ERROR] Plugin failed: {e}")
        raise

def main():
    # Parse input arguments
    args = parse_args()

    # Check -i (input URL) for a clearkey (#clearkey=)
    input_url, clearkey = check_clearkey(args.i)

    print(f"[INFO] Parsed URL: {input_url}")

    # Start Streamlink session
    session = Streamlink()

    # Apply the supplied user-agent string to streamlink session
    session.set_option("http-headers", {
        "User-Agent": args.ua
    })

    # Apply proxy server to streamlink if supplied using -proxy parameter
    if args.proxy:
        session.set_option("http-proxy", args.proxy)

    # Apply streamlink options that apply to all streams
    session.set_option("ffmpeg-fout", "mpegts") # Encode as mpegts when ffmpeg muxing (not matroska like default)
    session.set_option("ffmpeg-verbose", True) # Pass ffmpeg stderr through to streamlink
    session.set_option("stream-segment-threads", 4) # Number of threads for fetching segments
    session.set_option("hls-live-edge", 6) # Prebuffer n segments for HLS
    streams = None

    # If a clearkey is detected, prepare the stream for DRM decryption
    if clearkey:
        print(f"[INFO] ClearKey detected: {clearkey}")
        # Prepend dashdrm:// to input_url for dashdrm plugin matching
        input_url = f"dashdrm://{input_url}"
        # Load dashdrm plugin
        plugin = MPEGDASHDRM(session, input_url)
        # Set the dashdrm plugin options
        plugin.options["decryption-key"] = [clearkey] # pass clearkey tuple to plugin
        plugin.options["presentation-delay"] = 30 # Begin dash-drm streams n seconds behind live
        # session.set_option("ringbuffer-size", 67108864) # ringbuffer size (64M)
        # session.set_option("ffmpeg-loglevel", "debug")
        # Fetch the available streams
        try:
            streams = plugin.streams()
        except PluginError as e:
            print(f"[ERROR] Failed to load DRM plugin: {e}")
            return

    # For all other non-DRM/clearkey encrypted streams
    else:
        # Set session options for non-DRM streams
        session.set_option("ffmpeg-copyts", True) # Copy timestamps enabled for ffmpeg muxing
        session.set_option("hls-start-offset", 30) # Begin HLS streams n seconds behind live
        session.set_option("ffmpeg-start-at-zero", True) # Start at zero for ffmpeg muxing
        # Fetch the available streams
        try:
            streams = detect_stream_type(session, input_url, user_agent=args.ua, proxy=args.proxy)
        except Exception as e:
            print(f"[ERROR] Stream setup failed: {e}")
            return

    if not streams:
        print("[ERROR] No playable streams found.")
        return

    # Select best steam, live or iterate until one is found
    stream = streams.get("best") or streams.get("live") or next(iter(streams.values()), None)

    if not stream:
        print("[ERROR] No streams available.")
        return

    # Open stream and pipe to stdout

    try:
        with stream.open() as fd:
            while True:
                data = fd.read(1024)
                if not data:
                    break
                try:
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                except BrokenPipeError:
                    break
    except KeyboardInterrupt:
        print("[INFO] Stream interrupted, canceling.")

if __name__ == "__main__":
    main()
