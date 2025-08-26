#!/usr/bin/env python3

"""
Dispatchwrapparr - Version 1.1: A super wrapper for Dispatcharr

Usage: dispatchwrapper.py -i <URL> -ua <User Agent String>
Optional: -proxy <proxy server> -proxybypass <proxy bypass list> -clearkeys <json file/url> -cookies <txt file> -loglevel <level> -subtitles -novariantcheck -novideo -noaudio
"""

from __future__ import annotations

import os
import re
import sys
import signal
import itertools
import logging
import base64
import argparse
import requests
import fnmatch
import json
import subprocess
import http.cookiejar
from urllib.parse import urlparse, parse_qs
from collections import defaultdict
from contextlib import suppress, closing
from typing import List, Self, Tuple, Optional
from datetime import timedelta
from streamlink import Streamlink
from streamlink.exceptions import PluginError, FatalPluginError, NoPluginError
from streamlink.plugin import Plugin, pluginmatcher, pluginargument
from streamlink.plugin.plugin import HIGH_PRIORITY, parse_params, stream_weight
from streamlink.stream.dash import DASHStream, DASHStreamWorker, DASHStreamWriter, DASHStreamReader
from streamlink.stream.dash.manifest import MPD, Representation
from streamlink.stream.ffmpegmux import FFMPEGMuxer
from streamlink.stream import HTTPStream, HLSStream, DASHStream, MuxedStream, Stream
from streamlink.utils.url import update_scheme
from streamlink.session import Streamlink
from streamlink.utils.l10n import Language, Localization
from streamlink.utils.times import now

log = logging.getLogger("dispatchwrapparr")

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
    help="Enable subtitles"
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
                self._cmd.extend(["-readrate_initial_burst", "6"])
                self._cmd.extend(["-decryption_key", keys[key]])
                self._cmd.extend(["-copyts"])
                key += 1
                # If we had more streams than keys, start with the first
                # audio key again
                if key == len(keys):
                    key = 1
                self._cmd.extend([cmd, _])
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
            ret.append(("+".join(stream_name), stream))

        # rename duplicate streams
        dict_value_list = defaultdict(list)
        for k, v in ret:
            dict_value_list[k].append(v)

        def sortby_bandwidth(dash_stream: DASHStreamDRM) -> float:
            if dash_stream.video_representation:
                return dash_stream.video_representation.bandwidth
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

def parse_args():
    # Initial wrapper arguments
    parser = argparse.ArgumentParser(description="Dispatchwrapparr: A wrapper for Dispatcharr")
    parser.add_argument("-i", required=True, help="Input URL")
    parser.add_argument("-ua", required=True, help="User-Agent string")
    parser.add_argument("-proxy", help="Optional: HTTP proxy server (e.g. http://127.0.0.1:8888)")
    parser.add_argument("-proxybypass", help="Optional: Comma-separated list of hostnames or IP patterns to bypass the proxy (e.g. '192.168.*.*,*.lan')")
    parser.add_argument("-clearkeys", help="Optional: Supply a json file or URL containing URL/Clearkey maps (e.g. 'clearkeys.json' or 'https://some.host/clearkeys.json')")
    parser.add_argument("-cookies", help="Optional: Supply a cookie jar txt file in Mozilla/Netscape format (e.g. 'cookies.txt')")
    parser.add_argument("-subtitles", action="store_true", help="Optional: Enable support for subtitles (if available)")
    parser.add_argument("-novariantcheck", action="store_true", help="Optional: Do not autodetect if stream is audio-only or video-only")
    parser.add_argument("-novideo", action="store_true", help="Optional: Forces muxing of a blank video track into a stream that contains no audio")
    parser.add_argument("-noaudio", action="store_true", help="Optional: Forces muxing of a silent audio track into a stream that contains no video")
    parser.add_argument("-loglevel", type=str, default="INFO", choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"], help="Enable logging and set log level. (default: INFO)")
    args = parser.parse_args()

    # Enforce dependency for proxybypass, must be used with proxy (duh!!)
    if args.proxybypass and not args.proxy:
        parser.error("Argument -proxybypass: requires -proxy to be set")

    # Ensure that novariantcheck, novideo, and noaudio are not specified simultaneously
    flags = [args.novideo, args.noaudio, args.novariantcheck]
    if sum(bool(f) for f in flags) > 1:
        parser.error("Arguments -novariantcheck, -novideo and -noaudio can only be used individually")

    return args


def configure_logging(level="INFO") -> logging.Logger:
    """
    Set up console logging for both the script and Streamlink.

    Args:
        level (str): Logging level. One of: "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET".

    Returns:
        logging.Logger: Configured logger instance.
    """
    level = level.upper()
    numeric_level = getattr(logging, level, logging.INFO)

    # Set root logger (used by Streamlink internally)
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    if not root_logger.handlers:
        formatter = logging.Formatter("[%(name)s] %(asctime)s [%(levelname)s] %(message)s")
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root_logger.addHandler(console)

    # Ensure streamlink logger is not being filtered or silenced
    streamlink_log = logging.getLogger("streamlink")
    streamlink_log.setLevel(numeric_level)
    streamlink_log.propagate = True

    # Your application logger
    log = logging.getLogger("dispatchwrapparr")
    return log

def proxy_bypass_req(url: str, headers: dict, cookies: dict, bypasslist: str) -> str | None:
    """
    Determines what to do with supplied -proxybypass list
    - If supplied URL's hostname is not in bypass list, return the same URL and use proxy.
    - If '200' OK received, return 'None'. Main function will remove the proxy server for the given URL for processing.
    - If '301' or '302' redirector occurs, follow redirects until proxy bypass list no longer matches hostname, then return the new URL.
    - If any other HTTP code is received, throw an error and fallback to the original URL and continue to use proxy.
    """

    bypass_patterns = [pattern.strip() for pattern in bypasslist.split(",")]

    try:
        # First check: is original host in bypass list?
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname or not any(fnmatch.fnmatch(hostname, pat) for pat in bypass_patterns):
            return url  # hostname not in bypass list — use proxy

        # Hostname *is* in bypass list, begin checking for redirects
        while True:
            response = requests.get(url, headers=headers, cookies=cookies, allow_redirects=False, timeout=5)
            status = response.status_code

            if status == 200:
                return None  # good response, no proxy needed
            elif status in (301, 302):
                location = response.headers.get("Location")
                if not location:
                    break
                next_host = urlparse(location).hostname
                if next_host and any(fnmatch.fnmatch(next_host, pat) for pat in bypass_patterns):
                    url = location
                    continue
                else:
                    return location  # left bypass list
            else:
                return url  # unexpected code, return original
    except Exception as e:
        log.warning(f"proxy_bypass_req failed: {e}")
        return url  # fallback to original

def check_clearkeys_for_url(stream_url: str, clearkeys_source: str = None) -> str | None:
    """
    Return the ClearKey string from JSON mapping for the given stream URL.
    Supports wildcard pattern matching. Defaults to ./clearkeys.json.

    Args:
        stream_url (str): The stream URL to look up.
        clearkeys_source (str, optional): Local file path or URL. Defaults to 'clearkeys.json' in same directory as dispatchwrapparr.py.

    Returns:
        str or None: ClearKey string, or None if not found.
    """

    def is_url(path_or_url):
        parsed = urlparse(path_or_url)
        return parsed.scheme in ('http', 'https')

    def resolve_path(path: str) -> str:
        """
        Resolve a path to an absolute path.
        If the path is already absolute, return as-is.
        If it's relative, treat it as relative to the script's directory.
        """
        if os.path.isabs(path):
            return path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, path)

    log.info(f"Clearkeys Source: '{clearkeys_source}'")

    try:
        log.info(f"Attempting to load json data from '{clearkeys_source}'")
        if is_url(clearkeys_source):
            response = requests.get(clearkeys_source, timeout=10)
            response.raise_for_status()
            keymap = response.json()
        else:
            resolved_file = resolve_path(clearkeys_source)
            with open(resolved_file, "r") as f:
                keymap = json.load(f)
    except Exception as e:
        log.error(f"Failed to load ClearKey JSON from '{clearkeys_source}': {e}")
        return None

    # Wildcard pattern matching (case-insensitive)
    for pattern, clearkey in keymap.items():
        if fnmatch.fnmatchcase(stream_url.lower(), pattern.lower()):
            log.info(f"Clearkey(s) match for '{stream_url}': '{clearkey}'")
            return clearkey

    log.info(f"No matching clearkey(s) found for '{stream_url}'. Moving on.")
    return None

def check_url_fragments(raw_url: str):
    """
    Parses the input URL and extracts fragment parameters into a dictionary.

    Args:
        raw_url (str): The full URL, possibly with fragments.

    Returns:
        tuple: (base_url, fragment_dict) where fragment_dict is a dictionary of fragment key-value pairs,
               or None if no fragment is present.
    """
    parsed = urlparse(raw_url)

    base_url = parsed._replace(fragment="").geturl()
    fragment = parsed.fragment

    if fragment:
        # parse_qs returns a dict with values as lists
        parsed_fragments = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(fragment).items()}
        return base_url, parsed_fragments
    else:
        return base_url, None

def detect_stream_type(session, url, headers, proxy=None, cookies=None):
    """
    Tries to pass the URL directly to Streamlink, and if it cannot determine the stream type
    it makes a request to discover the MIME type and selects the appropriate stream type.

    Returns a dict of streams
    """
    try:
        return session.streams(url)
    except NoPluginError:
        log.warning("No plugin found for URL. Attempting fallback based on MIME type...")

        # Add a bytes range for GET so that it doesn't download too much
        headers["Range"] = "bytes=0-1023"

        proxies = {
            "http": proxy,
            "https": proxy
        } if proxy else None

        try:
            response = requests.get(
                url,
                headers=headers,
                cookies=cookies,
                proxies=proxies,
                stream=True,
                timeout=5
            )
            content_type = response.headers.get("Content-Type", "").lower()
            log.info(f"Detected Content-Type: {content_type}")
        except Exception as e:
            log.error(f"Could not detect stream type: {e}")
            raise

        if "vnd.apple.mpegurl" in content_type or "x-mpegurl" in content_type:
            return HLSStream.parse_variant_playlist(session, url)
        elif "dash+xml" in content_type:
            return DASHStream.parse_manifest(session, url)
        elif "video/mp2t" in content_type or "application/octet-stream" in content_type or "audio/mpeg" in content_type:
            return {"live": HTTPStream(session, url)}
        else:
            log.error("Unrecognized Content-Type for fallback")
            raise

    except PluginError as e:
        log.error(f"Plugin failed: {e}")
        raise

def create_silent_audio(session) -> Stream:
    """
    Return a Streamlink-compatible Stream that produces continuous silent AAC audio.
    Uses ffmpeg with anullsrc.
    """
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-c:a", "aac",
        "-f", "adts",
        "pipe:1"
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    class SilentAudioStream(Stream):
        def open(self, *args, **kwargs):
            return process.stdout

        def close(self):
            if process.poll() is None:
                process.kill()

    return SilentAudioStream(session)

def create_blank_video(session, resolution="320x180", fps=25, codec="libx264", bitrate="100k") -> Stream:
    """
    Create a Streamlink-compatible Stream that produces a blank video.
    Useful for muxing with audio-only streams.

    Args:
        session: Streamlink session instance
        resolution: Video resolution (default 320x180)
        fps: Frames per second (default 25)
        codec: Video codec (default libx264)
        bitrate: Target video bitrate (default 100k)
    """
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", f"color=size={resolution}:rate={fps}:color=black",
        "-c:v", codec,
        "-b:v", bitrate,
        "-f", "mpegts",
        "pipe:1"
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    class BlankVideoStream(Stream):
        def open(self, *args, **kwargs):
            return process.stdout

        def close(self):
            if process.poll() is None:
                process.kill()

    return BlankVideoStream(session)


def check_stream_variant(stream, session=None):
    """ Checks for different stream variants:
    Eg. Audio Only streams or Video streams with no audio
    Can be disabled by using the -nocheckvariant argument

    Returns integer:
    0 = Normal Audio/Video
    1 = Audio Only Stream (Radio streams)
    2 = Video Only Stream (Cameras or other livestreams with no audio)
    """

    # HLSStream case
    if isinstance(stream, HLSStream) and getattr(stream, "multivariant", None):
        log.debug("HLSStream Selected")
        # Find the playlist attributes by "best" selected url
        selected_playlist = None
        for playlist in stream.multivariant.playlists:
            if playlist.uri == stream.url:
                selected_playlist = playlist
                break

        if selected_playlist:
            codecs = selected_playlist.stream_info.codecs or []
            log.debug(f"Stream Codecs: {codecs}")
            # Check for audio/video presence
            has_video = any(c.startswith(("avc", "hev", "vp")) for c in codecs)
            has_audio = any(c.startswith(("mp4a", "aac")) for c in codecs)

            if has_audio and not has_video:
                log.debug("Detected Audio Only Stream")
                return 1
            elif has_video and not has_audio:
                log.debug("Detected Video Only Stream")
                return 2
            else:
                log.debug("Detected Audio+Video Stream")
                return 0

    # HTTPStream case
    if isinstance(stream, HTTPStream):
        log.debug("HTTPStream Selected")
        # Fast path: detect audio-only by extension
        url = stream.url.lower()
        if url.endswith((".aac", ".m4a", ".mp3", ".ogg")):
            log.debug(f"Detected Audio Only Stream by Extension: {url.endswith}")
            return 1
        if url.endswith((".mp4", ".mkv", ".webm", ".mov")):
            log.debug(f"Detected Video+Audio Stream by Extension: {url.endswith}")
            return 0
        # Safe path: check Content-Type via GET (stream=True) if session provided
        if session:
            try:
                with closing(session.http.get(stream.url, stream=True, timeout=5)) as r:
                    ctype = r.headers.get("Content-Type", "").lower()
                    if ctype.startswith("audio/"):
                        log.debug(f"Detected Audio Only Stream by Content-Type: {ctype}")
                        return 1
                    if ctype.startswith("video/"):
                        log.debug(f"Detected Video+Audio Stream by Content-Type: {ctype}")
                        return 0
            except Exception:
                # Ignore errors (405, timeout, etc.)
                return 0
        return 0

    # Default/fallback
    return 0

def load_cookies(cookiejar_path: str):
    """
    Load all cookies from a Netscape/Mozilla cookies.txt file
    and return:
      - cookies_dict: dict suitable for Streamlink or manual headers
      - cookies_requests: RequestsCookieJar for requests.Session
    """

    def resolve_path(path: str) -> str:
        if os.path.isabs(path):
            return path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, path)

    resolved_file = resolve_path(cookiejar_path)

    # Load cookie jar
    jar = http.cookiejar.MozillaCookieJar(resolved_file)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except FileNotFoundError:
        raise FileNotFoundError(f"Cookie file not found: {cookiejar_path}")
    except Exception as e:
        raise RuntimeError(f"Failed to load cookies from {cookiejar_path}: {e}")

    # Build dict and RequestsCookieJar
    cookies_dict = {}
    cookies_requests = requests.cookies.RequestsCookieJar()
    for c in jar:
        cookies_dict[c.name] = c.value
        cookies_requests.set(c.name, c.value, domain=c.domain, path=c.path, secure=c.secure, expires=c.expires)

    return cookies_dict, cookies_requests

def main():
    global log # allow assignment to the module-level variable

    args = parse_args() # Parse input arguments

    log = configure_logging(args.loglevel) # Configure logging
    log.info(f"Log Level: '{args.loglevel}'")

    input_url, fragments = check_url_fragments(args.i) # Check -i (input URL) for any fragments appended to url (#whatever=thing&#someotherthing=this).
    log.info(f"Stream URL: '{input_url}'")

    # Initialise vars
    clearkey = None
    referer = None
    origin = None
    cookies = None
    cookies_requests = None
    cookies_dict = None
    novariantcheck = None
    noaudio = None
    novideo = None

    # If there are fragments, set them safely
    if fragments:
        clearkey = fragments.get("clearkey")
        referer = fragments.get("referer")
        origin = fragments.get("origin")
        # Set novariantcheck, noaudio and novideo vars to True if fragments are true, else None
        novariantcheck = (fragments["novariantcheck"].lower() == "true") if "novariantcheck" in fragments else None
        noaudio = (fragments["noaudio"].lower() == "true") if "noaudio" in fragments else None
        novideo = (fragments["novideo"].lower() == "true") if "novideo" in fragments else None

    if args.proxy:
        log.info(f"HTTP Proxy: '{args.proxy}'")

    # Find clearkey if -clearkeys arg specified and one hasn't been found in fragments
    if clearkey is None and args.clearkeys:
        # If -clearkeys argument is supplied, search for a URL match in supplied file/url
        clearkey = check_clearkeys_for_url(input_url,args.clearkeys)

    # Check if novideo or noaudio are found in URL fragments, if not see if argument is supplied
    # The desired behaviour is that url fragments override any cli arguments
    if novariantcheck is None and args.novariantcheck:
        novariantcheck = args.novariantcheck
    if noaudio is None and args.noaudio:
        noaudio = args.noaudio
    if novideo is None and args.novideo:
        novideo = args.novideo

    # Begin header construction with mandatory user agent string
    log.info(f"User Agent: '{args.ua}'")
    headers = {
        "User-Agent": args.ua
    }

    # Append additional headers if set
    if referer:
        log.info(f"Referer: '{referer}'")
        headers["Referer"] = referer
    if origin:
        log.info(f"Origin: '{origin}'")
        headers["Origin"] = origin

    if args.cookies:
        # load cookies and create cookies_dict for streamlink, and cookies_requests for using with requests lib
        log.info(f"Cookies: Loading cookies from file '{args.cookies}'")
        cookies_dict,cookies_requests = load_cookies(args.cookies)

    # If -proxybypass is supplied, check url hostname matches any bypasses
    if args.proxybypass:
        log.info(f"Proxy Bypass: '{args.proxybypass}'")
        bypass_result = proxy_bypass_req(input_url, headers, cookies_requests, args.proxybypass)
        if bypass_result is None:
            log.info(f"Bypassing supplied proxy for stream URL: '{input_url}'")
            args.proxy = None
        else:
            input_url = bypass_result
            log.debug(f"Determined stream URL to proxy: '{input_url}'")

    # Start Streamlink session
    session = Streamlink()

    # Set cookies if enabled
    if args.cookies:
        session.set_option("http-cookies", cookies_dict)

    # Set streamlink headers
    log.debug(f"Headers: {headers}")
    session.set_option("http-headers", headers)

    # Apply proxy server to streamlink if supplied using -proxy parameter
    if args.proxy:
        session.set_option("http-proxy", args.proxy)
        # set ipv4 only mode when using proxy (fixes reliability issues)
        session.set_option("ipv4", True)

    # If -subtitles flag is set (mux-subtitles is False by default)
    if args.subtitles:
        log.info(f"Mux Subtitles: Enabled (may or may not work)")
        session.set_option("mux-subtitles", True)

    # If loglevel set as option, pass the same loglevel to ffmpeg
    python_loglevel = args.loglevel.upper() # Normalise the string and set python_loglevel var

    # Create a dict with python to ffmpeg loglevel equivalencies
    python_to_ffmpeg_loglevel = {
        "CRITICAL": "panic",
        "ERROR":    "error",
        "WARNING":  "warning",
        "INFO":     "info",
        "DEBUG":    "debug",
        "NOTSET":   "trace"
    }

    ffmpeg_loglevel = python_to_ffmpeg_loglevel.get(python_loglevel) # Set variable with the equivalent loglevel
    session.set_option("ffmpeg-loglevel", ffmpeg_loglevel) # Set the ffmpeg loglevel in the session options
    # Apply streamlink options that apply to all streams
    session.set_option("ffmpeg-verbose", True) # Pass ffmpeg stderr through to streamlink
    session.set_option("ffmpeg-fout", "mpegts") # Encode as mpegts when ffmpeg muxing (not matroska like default)
    session.set_option("ffmpeg-copyts", True) # Copy timestamps when muxing
    session.set_option("ffmpeg-start-at-zero", True) # Fix for initial stuttering of some streams
    session.set_option("stream-segment-threads", 2) # Number of threads for fetching segments

    streams = None
    # If a clearkey is detected, prepare the stream for DRM decryption
    if clearkey:
        log.info(f"Clearkey(s): '{clearkey}'")
        # Prepend dashdrm:// to input_url for dashdrm plugin matching
        input_url = f"dashdrm://{input_url}"
        # Load dashdrm plugin
        plugin = MPEGDASHDRM(session, input_url)
        # Set the dashdrm plugin options
        plugin.options["decryption-key"] = [clearkey] # pass clearkey tuple to plugin
        plugin.options["presentation-delay"] = 40 # Begin dash-drm streams n seconds behind live
        if args.subtitles:
            plugin.options["use-subtitles"]
        # Fetch the available streams
        try:
            streams = plugin.streams()
        except PluginError as e:
            log.error(f"Failed to load DRM plugin: {e}")
            return

    # For all other non-DRM/clearkey encrypted streams
    else:
        # Fetch the available streams
        try:
            streams = detect_stream_type(session, input_url, headers, proxy=args.proxy, cookies=cookies_requests) # Pass stream detection off to the detect_stream_type function
        except Exception as e:
            log.error(f"Stream setup failed: {e}")
            return

    # No streams found, log and error and exit
    if not streams:
        log.error("No playable streams found.")
        return

    # Select best steam, live or iterate until one is found
    log.info("Selecting best available stream.")
    stream = streams.get("best") or streams.get("live") or next(iter(streams.values()), None)

    # Stream not available, log error and exit
    if not stream:
        log.error("No streams available.")
        return

    # Do a variant check only if novideo and noaudio are None, or novariantcheck is True
    if novideo is None and noaudio is None and novariantcheck is None:
        # Attempt to detect stream variant automatically (Eg. Video Only or Audio Only)
        log.debug("Attempting to check stream variant")
        variant = check_stream_variant(stream,session)
        if variant == 1:
            log.info("Stream detected as audio only/no video")
            novideo = True
        if variant == 2:
            log.info("Stream detected as video only/no audio")
            noaudio = True
    else:
        log.info("Skipping stream variant check")

    if noaudio and not novideo:
        log.info("No Audio: Muxing silent audio into supplied video stream")
        audio_stream = create_silent_audio(session)
        video_stream = stream
        stream = MuxedStream(session, video_stream, audio_stream)

    elif not noaudio and novideo:
        log.info("No Video: Muxing blank video into supplied audio stream")
        audio_stream = stream
        video_stream = create_blank_video(session)
        stream = MuxedStream(session, video_stream, audio_stream)

    elif noaudio and novideo:
        log.warning("Both 'noaudio' and 'novideo' specified. Ignoring both.")

    try:
        log.info("Starting stream.")
        with stream.open() as fd:
            while True:
                data = fd.read(188 * 64) # Match buffer settings of Dispatcharr for optimal MPEG-TS buffering
                if not data:
                    break
                try:
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                except BrokenPipeError:
                    break
    except KeyboardInterrupt:
        log.info("Stream interrupted, canceling.")

# Set default SIGPIPE behavior so dispatchwrapparr exits cleanly when the pipe is closed
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

if __name__ == "__main__":
    main()
