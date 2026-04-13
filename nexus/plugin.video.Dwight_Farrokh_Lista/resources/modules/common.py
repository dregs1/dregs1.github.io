# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import io
import os
import time
try:
    import requests
except ImportError:
    import urllib.request

    class SimpleResponse:
        def __init__(self, data):
            self.text = data.decode('utf-8', 'ignore')

    class SimpleSession:
        def __init__(self):
            self.headers = {}

        def get(self, url, timeout=10):
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return SimpleResponse(resp.read())

    class requests:
        @staticmethod
        def Session():
            return SimpleSession()


try:
    from kodi_six import xbmc, xbmcaddon, xbmcvfs
except ImportError:
    import xbmc
    import xbmcaddon
    import xbmcvfs

try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except Exception:
    HTTPAdapter = None
    Retry = None

DEFAULT_TIMEOUT = 12
DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
)


def get_profile_dir():
    addon = xbmcaddon.Addon()
    return xbmcvfs.translatePath(addon.getAddonInfo('profile'))


def ensure_dir(path):
    if not path:
        return path
    try:
        if not os.path.exists(path):
            os.makedirs(path)
    except Exception:
        pass
    return path


PROFILE_DIR = ensure_dir(get_profile_dir())
LOG_FILE = os.path.join(PROFILE_DIR, 'Dwight_Farrokh_Lista.debug.log')


def _to_text(value):
    if value is None:
        return ''
    try:
        if isinstance(value, bytes):
            return value.decode('utf-8', 'replace')
    except Exception:
        pass
    try:
        return str(value)
    except Exception:
        return repr(value)


def log(message, level=None):
    if level is None:
        level = xbmc.LOGINFO
    text = '[OnePlay] {}'.format(_to_text(message))
    try:
        xbmc.log(text, level=level)
    except Exception:
        pass
    try:
        ensure_dir(PROFILE_DIR)
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        with io.open(LOG_FILE, 'a', encoding='utf-8') as fh:
            fh.write(u'{} {}\n'.format(timestamp, _to_text(message)))
    except Exception:
        pass


def make_session(user_agent=None, retries=2):
    session = requests.Session()
    session.headers.update({'User-Agent': user_agent or DEFAULT_USER_AGENT})
    if HTTPAdapter and Retry:
        try:
            retry = Retry(
                total=retries,
                connect=retries,
                read=retries,
                backoff_factor=0.35,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=frozenset(['GET', 'HEAD'])
            )
        except TypeError:
            retry = Retry(
                total=retries,
                connect=retries,
                read=retries,
                backoff_factor=0.35,
                status_forcelist=[429, 500, 502, 503, 504],
                method_whitelist=frozenset(['GET', 'HEAD'])
            )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
    return session
