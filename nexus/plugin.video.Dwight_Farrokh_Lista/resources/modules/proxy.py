# -*- coding: utf-8 -*-
import urllib.parse
try:
    import requests
    from requests.exceptions import ConnectionError, RequestException, ReadTimeout, ChunkedEncodingError
except ImportError:
    import urllib.request
    import urllib.error

    class RequestException(Exception):
        pass

    class ConnectionError(RequestException):
        pass

    class ReadTimeout(RequestException):
        pass

    class ChunkedEncodingError(RequestException):
        pass

    class FakeResponse:
        def __init__(self, response):
            self.raw = response
            self.status_code = response.getcode()
            self.headers = dict(response.getheaders())
            self.url = response.geturl()
            self.content = response.read()

        def iter_content(self, chunk_size=4096):
            for i in range(0, len(self.content), chunk_size):
                yield self.content[i:i+chunk_size]

        def close(self):
            try:
                self.raw.close()
            except:
                pass

    class FakeSession:
        def get(self, url, headers=None, allow_redirects=True, stream=False, timeout=None):
            try:
                req = urllib.request.Request(url, headers=headers or {})
                resp = urllib.request.urlopen(req, timeout=timeout[1] if isinstance(timeout, tuple) else timeout)
                return FakeResponse(resp)
            except urllib.error.URLError as e:
                raise ConnectionError(str(e))

        def close(self):
            pass

    class requests:
        Session = FakeSession
import binascii
import os
import re
import time
import logging
import threading
import socket
import sys

try:
    import xbmc
    import xbmcaddon
except ImportError:
    from kodi_six import xbmc, xbmcaddon

from urllib.parse import urljoin
try:
    from http.client import IncompleteRead
except ImportError:
    class IncompleteRead(Exception):
        pass

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn
except ImportError:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer  # type: ignore
    from SocketServer import ThreadingMixIn  # type: ignore

PORT = 8088
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

IP_CACHE_TS = {}
IP_CACHE_MP4 = {}
AGENT_OF_CHAOS = {}
COUNT_CLEAR = {}
_SERVER_THREAD = None
_SERVER_STARTED = False
_SERVER = None

_TS_STATUS_LOG = {}
_ORIGIN_HEALTH = {}
_LOG_BURSTS = {}
_SESSION_CACHE = {
    'good_hosts': {},
    'bad_hosts': {},
    'working_user_agent': {},
    'last_working_url': {},
    'content_type': {},
    'source_profile': {},
}
_SETTINGS_CACHE = {'ts': 0, 'addon': None, 'mode': 'balance', 'xtream_hardening': True, 'host_memory': True, 'debug': False}
_USER_AGENT_POOL = [
    DEFAULT_USER_AGENT,
    'Mozilla/5.0 (Linux; Android 10; SM-A505G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
    'ExoPlayerLib/2.18.7',
]
_PROXY_POLICIES = {
    'fast': {'hls_max_retries': 5, 'ts_max_retries': 999999, 'timeout_connect': 4, 'timeout_read': 10, 'cooldown_base': 0.10},
    'balance': {'hls_max_retries': 7, 'ts_max_retries': 999999, 'timeout_connect': 5, 'timeout_read': 15, 'cooldown_base': 0.15},
    'stable': {'hls_max_retries': 9, 'ts_max_retries': 999999, 'timeout_connect': 6, 'timeout_read': 18, 'cooldown_base': 0.20},
}

# Silencia o root logger para evitar spam no kodi.log e usa xbmc.log para eventos úteis.
_root_logger = logging.getLogger()
try:
    _root_logger.handlers = []
except Exception:
    pass
_root_logger.setLevel(logging.CRITICAL)
for _name in ('werkzeug', 'urllib3', 'requests'):
    try:
        _lg = logging.getLogger(_name)
        _lg.handlers = []
        _lg.propagate = False
        _lg.setLevel(logging.CRITICAL)
    except Exception:
        pass

for _mod in list(sys.modules):
    if _mod.startswith('flask') or _mod.startswith('werkzeug') or _mod.startswith('netunblock'):
        try:
            del sys.modules[_mod]
        except Exception:
            pass


def _safe_text(value):
    try:
        return str(value)
    except Exception:
        try:
            return repr(value)
        except Exception:
            return 'erro_desconhecido'


def _emit_log(message, level=logging.INFO):
    try:
        if level >= logging.ERROR:
            xbmc.log('[OnePlayProxy] ' + message, level=xbmc.LOGERROR)
        elif level >= logging.WARNING:
            xbmc.log('[OnePlayProxy] ' + message, level=xbmc.LOGWARNING)
        elif level >= logging.INFO:
            xbmc.log('[OnePlayProxy] ' + message, level=xbmc.LOGINFO)
        else:
            xbmc.log('[OnePlayProxy] ' + message, level=xbmc.LOGDEBUG)
    except Exception:
        pass


def _throttled_log(key, interval, level, message):
    now = time.time()
    last = _TS_STATUS_LOG.get(key, 0)
    if (now - last) >= interval:
        _TS_STATUS_LOG[key] = now
        _emit_log(message, level)


def _burst_log(key, window, level, template):
    now = time.time()
    item = _LOG_BURSTS.get(key)
    if not item or (now - item['start']) > window:
        item = {'start': now, 'count': 0}
    item['count'] += 1
    _LOG_BURSTS[key] = item
    if item['count'] == 1:
        _emit_log(template % 1, level)
    elif item['count'] in (5, 15, 30) or (now - item['start']) >= window:
        _emit_log(template % item['count'], level)
        item['start'] = now
        item['count'] = 0


def _log_ts_status_once(status_code):
    _burst_log('status:%s' % status_code, 45, logging.INFO, '[TS Downloader] HTTP %s recorrente; %sx no período.')


def _log(msg, level=None):
    try:
        if level is None:
            level = xbmc.LOGINFO
        # evita poluir produção com debug sem perder mensagens úteis
        if level == xbmc.LOGDEBUG and not _settings_snapshot().get('debug'):
            return
        xbmc.log('[OnePlayProxy] ' + msg, level=level)
    except Exception:
        pass


def _addon_handle():
    now = time.time()
    if _SETTINGS_CACHE.get('addon') is not None and (now - _SETTINGS_CACHE.get('ts', 0)) < 30:
        return _SETTINGS_CACHE.get('addon')
    try:
        _SETTINGS_CACHE['addon'] = xbmcaddon.Addon('plugin.video.OnePlay.Matrix')  # type: ignore[name-defined]
        _SETTINGS_CACHE['ts'] = now
    except Exception:
        _SETTINGS_CACHE['addon'] = None
    return _SETTINGS_CACHE.get('addon')


def _settings_snapshot(force=False):
    now = time.time()
    if not force and (now - _SETTINGS_CACHE.get('ts', 0)) < 10:
        return _SETTINGS_CACHE
    addon = _addon_handle()
    mode = 'balance'
    xtream_hardening = True
    host_memory = True
    debug = False
    try:
        if addon:
            raw = (addon.getSetting('proxy_mode') or '').strip().lower()
            enum_map = {'0': 'fast', '1': 'balance', '2': 'stable', 'rápido': 'fast', 'rapido': 'fast', 'balanceado': 'balance', 'estável': 'stable', 'estavel': 'stable'}
            raw = enum_map.get(raw, raw)
            if raw in _PROXY_POLICIES:
                mode = raw
            xtream_hardening = (addon.getSetting('proxy_xtream_hardening') or 'true').lower() == 'true'
            host_memory = (addon.getSetting('proxy_host_memory') or 'true').lower() == 'true'
            debug = (addon.getSetting('proxy_debug') or 'false').lower() == 'true'
    except Exception:
        pass
    _SETTINGS_CACHE.update({'ts': now, 'mode': mode, 'xtream_hardening': xtream_hardening, 'host_memory': host_memory, 'debug': debug})
    return _SETTINGS_CACHE


def _get_mode():
    mode = _settings_snapshot().get('mode', 'balance')
    return mode if mode in _PROXY_POLICIES else 'balance'


def _policy():
    return _PROXY_POLICIES.get(_get_mode(), _PROXY_POLICIES['balance'])


def _classify_source(url):
    try:
        parsed = urllib.parse.urlparse(url or '')
        host = (parsed.netloc or '').lower()
        path = (parsed.path or '').lower()
        query = (parsed.query or '').lower()
    except Exception:
        host = path = query = ''
    joined = '%s%s?%s' % (host, path, query)
    is_ts = path.endswith('.ts') or '/hls/' in path or '/hl' in path
    is_m3u8 = path.endswith('.m3u8') or 'mpegurl' in joined
    tokenized = 'token=' in query or 'wmsauth' in query or 'auth=' in query
    is_xtream = '/live/' in path or '/hls/' in path or '/movie/' in path or '/series/' in path or tokenized
    bad_xtream = is_xtream and (is_ts or is_m3u8) and tokenized
    if bad_xtream:
        return 'xtream_bad'
    if is_xtream:
        return 'xtream_good'
    if is_m3u8:
        return 'hls_generic'
    if is_ts:
        return 'ts_generic'
    return 'generic'


def _source_profile(url):
    profile = _classify_source(url)
    if _settings_snapshot().get('host_memory'):
        host = _host_from_url(url)
        cached = _SESSION_CACHE['source_profile'].get(host)
        if cached:
            profile = cached
    return profile


def _remember_source_profile(url, profile):
    host = _host_from_url(url)
    if host and profile:
        _SESSION_CACHE['source_profile'][host] = profile


def _host_from_url(url):
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ''


def _host_stats(host):
    item = _SESSION_CACHE['good_hosts'].get(host)
    if item is None:
        item = {'success_count': 0, 'fail_count': 0, 'cooldown_until': 0, 'last_error': '', 'last_success': 0}
        _SESSION_CACHE['good_hosts'][host] = item
    return item


def _host_is_available(host):
    if not host:
        return True
    return time.time() >= _host_stats(host).get('cooldown_until', 0)


def _host_backoff(host):
    if not host:
        return
    item = _host_stats(host)
    wait = item.get('cooldown_until', 0) - time.time()
    if wait > 0:
        time.sleep(min(0.8, wait))


def _mark_host_ok(host, final_url=None, user_agent=None, content_type=None):
    if not host or not _settings_snapshot().get('host_memory'):
        return
    item = _host_stats(host)
    item['success_count'] = item.get('success_count', 0) + 1
    item['fail_count'] = 0
    item['cooldown_until'] = 0
    item['last_error'] = ''
    item['last_success'] = time.time()
    _SESSION_CACHE['bad_hosts'].pop(host, None)
    if final_url:
        _SESSION_CACHE['last_working_url'][host] = final_url
    if user_agent:
        _SESSION_CACHE['working_user_agent'][host] = user_agent
    if content_type:
        _SESSION_CACHE['content_type'][host] = content_type


def _mark_host_fail(host, err='unknown', soft=False):
    if not host or not _settings_snapshot().get('host_memory'):
        return
    item = _host_stats(host)
    item['fail_count'] = item.get('fail_count', 0) + 1
    item['last_error'] = str(err)
    base = _policy().get('cooldown_base', 0.15)
    threshold = 5 if soft else 3
    if item['fail_count'] >= threshold:
        item['cooldown_until'] = time.time() + min(3.0, base * item['fail_count'])
        _SESSION_CACHE['bad_hosts'][host] = item['cooldown_until']


def _smart_retry_delay(err_kind, attempt):
    if err_kind == '406':
        return min(0.45, 0.08 * max(1, attempt))
    if err_kind == 'timeout':
        return min(1.0, 0.20 * max(1, attempt))
    if err_kind == 'connection':
        return min(0.8, 0.16 * max(1, attempt))
    return min(0.75, 0.14 * max(1, attempt))


def _pick_user_agent(host, reconnects=0, prefer_stream=False):
    if host and reconnects <= 1:
        cached = _SESSION_CACHE['working_user_agent'].get(host)
        if cached:
            return cached
    idx = reconnects % len(_USER_AGENT_POOL)
    ua = _USER_AGENT_POOL[idx]
    if prefer_stream and reconnects >= 3:
        ua = 'Lavf/60.3.100'
    return ua


def _validate_upstream_response(response, expect_playlist=False, expect_stream=False, url=''):
    try:
        ctype = (response.headers.get('content-type') or '').lower()
    except Exception:
        ctype = ''
    if response.status_code not in (200, 206):
        return False, ctype
    if 'text/html' in ctype and not expect_playlist:
        return False, ctype
    if expect_stream and ('json' in ctype or 'xml' in ctype):
        return False, ctype
    profile = _source_profile(url)
    if expect_stream and profile == 'xtream_bad':
        # origem ruim costuma mentir no content-type; aceita octet/text genérico se a URL é claramente stream
        if not ctype or 'application/octet-stream' in ctype or 'video/' in ctype or 'audio/' in ctype or 'text/plain' in ctype:
            return True, ctype or 'application/octet-stream'
    return True, ctype


def _dns_override():
    try:
        from doh import DNSOverrideDoH
        DNSOverrideDoH()
        return
    except Exception:
        pass
    try:
        from resources.lib.dns import customdns
        customdns()
    except Exception:
        pass


def _get_client_ip(headers, client_address):
    forwarded_for = headers.get('X-Forwarded-For')
    real_ip = headers.get('X-Real-IP')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    if real_ip:
        return real_ip
    return client_address[0] if client_address else '127.0.0.1'


def _get_cache_key(client_ip, url):
    return '%s:%s' % (client_ip, url)


def _origin_key(url):
    try:
        p = urllib.parse.urlparse(url)
        return '%s://%s' % (p.scheme or 'http', p.netloc or '')
    except Exception:
        return url or 'unknown'


def _origin_state(url):
    key = _origin_key(url)
    state = _ORIGIN_HEALTH.get(key)
    now = time.time()
    if not state or (now - state.get('updated', 0)) > 180:
        state = {
            'updated': now,
            'fail_count': 0,
            '406_count': 0,
            'timeout_count': 0,
            'good_count': 0,
            'cooldown_until': 0,
            'last_error': ''
        }
        _ORIGIN_HEALTH[key] = state
    return state


def _mark_origin_ok(url):
    state = _origin_state(url)
    state['updated'] = time.time()
    state['good_count'] = state.get('good_count', 0) + 1
    state['fail_count'] = 0
    state['406_count'] = 0
    state['timeout_count'] = 0
    state['last_error'] = ''
    state['cooldown_until'] = 0


def _mark_origin_fail(url, code=None, exc_name=None):
    state = _origin_state(url)
    state['updated'] = time.time()
    state['fail_count'] = state.get('fail_count', 0) + 1
    if code == 406:
        state['406_count'] = state.get('406_count', 0) + 1
    if exc_name in ('ReadTimeout', 'ConnectionError', 'ChunkedEncodingError'):
        state['timeout_count'] = state.get('timeout_count', 0) + 1
    state['last_error'] = str(code or exc_name or 'unknown')
    fail_count = state.get('fail_count', 0)
    if fail_count >= 6:
        cooldown = min(2.0, 0.15 * fail_count)
        state['cooldown_until'] = time.time() + cooldown


def _apply_origin_cooldown(url):
    state = _origin_state(url)
    now = time.time()
    cooldown_until = state.get('cooldown_until', 0)
    if cooldown_until > now:
        time.sleep(min(0.75, cooldown_until - now))


def _build_upstream_headers(original_headers, reconnects=0, response_code=None, prefer_stream=False, url=''):
    headers = dict(original_headers or {})
    profile = _source_profile(url)
    headers.pop('Host', None)
    headers.pop('Connection', None)
    headers.pop('Content-Length', None)

    if reconnects > 0:
        headers.setdefault('User-Agent', DEFAULT_USER_AGENT)
        headers['Connection'] = 'close'

    if prefer_stream:
        headers.setdefault('Accept', '*/*')
        headers['Icy-MetaData'] = '1'
        headers['Accept-Encoding'] = 'identity'

    if profile == 'xtream_bad' and _settings_snapshot().get('xtream_hardening'):
        headers.pop('Range', None)
        headers.pop('If-None-Match', None)
        headers.pop('If-Modified-Since', None)
        headers['Accept'] = '*/*'
        headers['Accept-Encoding'] = 'identity'
        headers['Connection'] = 'close'

    if response_code == 406:
        for noisy in ('Accept', 'Accept-Language', 'Origin', 'Referer', 'Sec-Fetch-Dest', 'Sec-Fetch-Mode', 'Sec-Fetch-Site'):
            headers.pop(noisy, None)
        headers['Accept'] = '*/*'
        headers['Connection'] = 'close'
        if reconnects >= 2:
            headers.pop('Range', None)
        if reconnects >= 3 and profile != 'xtream_bad':
            headers['User-Agent'] = binascii.b2a_hex(os.urandom(20))[:32].decode('ascii')

    if reconnects >= 4:
        headers.pop('Accept-Encoding', None)
        headers['Cache-Control'] = 'no-cache'
        headers['Pragma'] = 'no-cache'

    return headers



def _timeout_tuple(url, prefer_stream=False):
    policy = _policy()
    connect = policy.get('timeout_connect', 5)
    read = policy.get('timeout_read', 15)
    profile = _source_profile(url)
    if profile == 'xtream_bad' and _settings_snapshot().get('xtream_hardening'):
        return (min(connect, 4), max(read, 20 if prefer_stream else 12))
    if profile == 'xtream_good':
        return (connect, max(read, 16 if prefer_stream else read))
    if profile == 'hls_generic' and prefer_stream:
        return (connect, max(read, 18))
    return (connect, read)


def _is_probably_live_segment(url):
    u = (url or '').lower()
    return '.ts' in u or '/hls/' in u or '/hl' in u

def _rewrite_m3u8_urls(playlist_content, base_url, host):
    def replace_url(match):
        segment_url = match.group(0).strip()
        if segment_url.startswith('#') or not segment_url or segment_url == '/':
            return segment_url
        try:
            absolute_url = urljoin(base_url + '/', segment_url)
            if not (absolute_url.endswith('.ts') or '/hl' in absolute_url.lower() or absolute_url.endswith('.m3u8')):
                logging.debug('[HLS Proxy] Ignorando URL inválida no m3u8: %s' % absolute_url)
                return segment_url
            proxied_url = 'http://%s/hlsretry?url=%s' % (host, urllib.parse.quote(absolute_url, safe=''))
            return proxied_url
        except ValueError as e:
            logging.debug('[HLS Proxy] Erro ao resolver URL %s: %s' % (segment_url, e))
            return segment_url
    return re.sub(r'^(?!#)\S+', replace_url, playlist_content, flags=re.MULTILINE)


def _stream_response(response, client_ip, url, sess):
    cache_key = _get_cache_key(client_ip, url) if any(ext in url.lower() for ext in ['.mp4', '.m3u8']) else client_ip
    mode_ts = [False]

    def generate_chunks():
        bytes_read = 0
        try:
            for chunk in response.iter_content(chunk_size=4096):
                if not chunk:
                    continue
                bytes_read += len(chunk)
                if '.mp4' in url.lower():
                    IP_CACHE_MP4.setdefault(cache_key, []).append(chunk)
                    if len(IP_CACHE_MP4[cache_key]) > 20:
                        IP_CACHE_MP4[cache_key].pop(0)
                elif '.ts' in url.lower() or '/hl' in url.lower():
                    mode_ts[0] = True
                    IP_CACHE_TS.setdefault(cache_key, []).append(chunk)
                    if len(IP_CACHE_TS[cache_key]) > 20:
                        IP_CACHE_TS[cache_key].pop(0)
                yield chunk
        except (IncompleteRead, ConnectionError) as e:
            logging.debug('[HLS Proxy] Erro ao processar chunks (bytes lidos: %d): %s' % (bytes_read, e))
            cache = IP_CACHE_TS if mode_ts[0] else IP_CACHE_MP4
            for chunk in cache.get(cache_key, [])[-5:]:
                yield chunk
        finally:
            try:
                sess.close()
            except Exception:
                pass
    return generate_chunks()


def _stream_cache(client_ip, url):
    if not url:
        return None
    cache_key = _get_cache_key(client_ip, url) if any(ext in url.lower() for ext in ['.mp4', '.m3u8']) else client_ip
    if '.mp4' in url.lower():
        cache = IP_CACHE_MP4
    elif '.ts' in url.lower() or '/hl' in url.lower():
        cache = IP_CACHE_TS
    else:
        cache = None
    if not cache:
        return None

    def generate_cached_chunks():
        if cache_key in cache:
            for chunk in cache.get(cache_key, [])[-5:]:
                yield chunk
        else:
            logging.debug('[HLS Proxy] Cache vazio para %s' % cache_key)
    return generate_cached_chunks()


class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def handle(self):
        try:
            BaseHTTPRequestHandler.handle(self)
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass

    def finish(self):
        try:
            BaseHTTPRequestHandler.finish(self)
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass

    def log_message(self, format, *args):
        return

    def _send_json(self, payload, status=200):
        data = payload.encode('utf-8') if isinstance(payload, str) else payload
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Connection', 'close')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def _send_text(self, payload, status=200, content_type='text/plain; charset=utf-8'):
        data = payload.encode('utf-8') if isinstance(payload, str) else payload
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Connection', 'close')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def do_GET(self):
        self._dispatch()

    def do_HEAD(self):
        self._dispatch(head_only=True)

    def _dispatch(self, head_only=False):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == '/':
            self._send_json('{"message": "OnePlay Proxy nativo ativo"}')
            return
        if path == '/hlsretry':
            self._handle_hlsretry(parsed, head_only=head_only)
            return
        if path == '/tsdownloader':
            self._handle_tsdownloader(parsed, head_only=head_only)
            return
        self._send_text('Not Found', status=404)

    def _filtered_request_headers(self):
        upstream = {}
        for k, v in self.headers.items():
            lk = k.lower()
            if lk in ('host', 'content-length', 'connection'):
                continue
            upstream[k] = v
        return upstream

    def _handle_hlsretry(self, parsed, head_only=False):
        _dns_override()
        params = urllib.parse.parse_qs(parsed.query)
        url = params.get('url', [None])[0]
        if url:
            url = urllib.parse.unquote(url)
        client_ip = _get_client_ip(self.headers, self.client_address)
        cache_key = _get_cache_key(client_ip, url) if url and any(x in url.lower() for x in ['.mp4', '.m3u8']) else client_ip
        if not url:
            self._send_json('{"detail": "No URL provided"}', status=400)
            return

        session = requests.Session()
        original_headers = self._filtered_request_headers()

        max_retries = _policy().get('hls_max_retries', 7)
        attempts = 0
        tried_without_range = False
        media_type = 'video/mp4' if '.mp4' in url.lower() else 'video/mp2t' if '.ts' in url.lower() or '/hl' in url.lower() else 'application/octet-stream'
        response_headers = {}
        status = 200
        last_status = None

        while attempts < max_retries:
            response = None
            headers = _build_upstream_headers(original_headers, reconnects=attempts, response_code=last_status, url=url)
            try:
                _apply_origin_cooldown(url)
                range_header = headers.get('Range')
                if '.mp4' in url.lower() and range_header and tried_without_range:
                    headers.pop('Range', None)

                if AGENT_OF_CHAOS.get(cache_key) and '.ts' not in url.lower() and '/hl' not in url.lower():
                    headers['User-Agent'] = AGENT_OF_CHAOS.get(cache_key, DEFAULT_USER_AGENT)
                elif '.ts' in url.lower() or '/hl' in url.lower():
                    headers.setdefault('User-Agent', DEFAULT_USER_AGENT)

                host = _host_from_url(url)
                if not _host_is_available(host):
                    _host_backoff(host)
                headers['User-Agent'] = _pick_user_agent(host, attempts, prefer_stream=('.ts' in url.lower() or '/hl' in url.lower()))
                response = session.get(url, headers=headers, allow_redirects=True, stream=True, timeout=_timeout_tuple(url, prefer_stream=(_is_probably_live_segment(url) or '.mp4' in url.lower())))

                ok_response, content_type = _validate_upstream_response(response, expect_playlist=('.m3u8' in url.lower()), expect_stream=('.ts' in url.lower() or '/hl' in url.lower() or '.mp4' in url.lower()), url=url)
                if ok_response:
                    _mark_origin_ok(response.url or url)
                    _mark_host_ok(_host_from_url(response.url or url), final_url=(response.url or url), user_agent=headers.get('User-Agent'), content_type=content_type)
                    _remember_source_profile(response.url or url, _classify_source(response.url or url))
                    if '.mp4' in url.lower() or '.m3u8' in url.lower():
                        url = response.url
                    if client_ip in COUNT_CLEAR:
                        if COUNT_CLEAR.get(client_ip, 0) > 4:
                            try:
                                AGENT_OF_CHAOS.pop(cache_key, None)
                                IP_CACHE_MP4.pop(cache_key, None)
                                IP_CACHE_TS.pop(cache_key, None)
                            except Exception:
                                pass
                    if client_ip not in COUNT_CLEAR:
                        COUNT_CLEAR[client_ip] = 0
                    elif int(COUNT_CLEAR.get(client_ip, 0) > 4):
                        COUNT_CLEAR[client_ip] = 0
                    else:
                        COUNT_CLEAR[client_ip] = COUNT_CLEAR.get(client_ip, 0) + 1

                    content_type = content_type or response.headers.get('content-type', '').lower()
                    if ('mpegurl' in content_type or 'x-directory/normal' in content_type or '.m3u8' in url.lower()):
                        base_url = url.rsplit('/', 1)[0]
                        playlist_content = response.content.decode('utf-8', errors='ignore')
                        host = self.headers.get('Host', '127.0.0.1:%d' % PORT)
                        rewritten = _rewrite_m3u8_urls(playlist_content, base_url, host)
                        self._send_text(rewritten, content_type='application/vnd.apple.mpegurl')
                        return

                    if '/hl' in url.lower() and '_' in url.lower() and '.ts' in url.lower():
                        try:
                            seg_ = re.findall(r'_(.*?)\.ts', url)[0]
                            seg_before = '_%s.ts' % seg_
                            seg_after = '_%s.ts' % str(int(seg_) + 1)
                            url = url.replace(seg_before, seg_after)
                        except Exception:
                            pass

                    media_type = 'video/mp4' if '.mp4' in url.lower() else 'video/mp2t' if '.ts' in url.lower() or '/hl' in url.lower() else response.headers.get('content-type', 'application/octet-stream')
                    response_headers = {k: v for k, v in response.headers.items() if k.lower() in ['content-type', 'accept-ranges', 'content-range']}
                    status = 206 if response.status_code == 206 else 200

                    self.send_response(status)
                    self.send_header('Content-Type', media_type)
                    for k, v in response_headers.items():
                        if k.lower() == 'content-type':
                            continue
                        self.send_header(k, v)
                    self.send_header('Connection', 'close')
                    self.end_headers()

                    if head_only:
                        try:
                            response.close()
                        except Exception:
                            pass
                        try:
                            session.close()
                        except Exception:
                            pass
                        return

                    for chunk in _stream_response(response, client_ip, url, session):
                        try:
                            self.wfile.write(chunk)
                        except Exception:
                            return
                    return

                elif response.status_code == 416 and range_header and not tried_without_range:
                    tried_without_range = True
                    last_status = 416
                    try:
                        response.close()
                    except Exception:
                        pass
                    continue
                else:
                    last_status = response.status_code
                    _mark_origin_fail(response.url or url, code=response.status_code)
                    AGENT_OF_CHAOS[cache_key] = binascii.b2a_hex(os.urandom(20))[:32].decode('ascii')
                    attempts += 1
                    if response.status_code == 406:
                        _burst_log('hls-406:%s' % _origin_key(url), 60, logging.INFO, '[HLS Proxy] Origem respondeu 406; fallback discreto acionado (%sx).')
                        time.sleep(min(0.50, 0.15 * attempts))
                    else:
                        level = logging.INFO if _source_profile(url) == 'xtream_bad' else logging.WARNING
                        _throttled_log('hls-status:%s:%s' % (_origin_key(url), response.status_code), 20, level, '[HLS Proxy] Resposta HTTP %s da origem.' % response.status_code)
                        time.sleep(min(0.65, 0.18 * attempts))
                    if '.ts' in url.lower() or '/hl' in url.lower() or '.mp4' in url.lower():
                        self.send_response(status)
                        self.send_header('Content-Type', media_type)
                        for k, v in response_headers.items():
                            if k.lower() == 'content-type':
                                continue
                            self.send_header(k, v)
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        if not head_only:
                            for chunk in (_stream_cache(client_ip, url) or []):
                                try:
                                    self.wfile.write(chunk)
                                except Exception:
                                    return
                        return
            except RequestException as e:
                last_status = e.__class__.__name__
                _mark_origin_fail(url, exc_name=e.__class__.__name__)
                _mark_host_fail(_host_from_url(url), err=e.__class__.__name__, soft=(e.__class__.__name__ in ('ReadTimeout','ConnectionError','ChunkedEncodingError')))
                AGENT_OF_CHAOS[cache_key] = binascii.b2a_hex(os.urandom(20))[:32].decode('ascii')
                attempts += 1
                lvl = logging.INFO if _source_profile(url) == 'xtream_bad' else logging.WARNING
                _throttled_log('hls-exc:%s:%s' % (_origin_key(url), e.__class__.__name__), 15, lvl, '[HLS Proxy] Origem instável; retry inteligente em curso (%s).' % _safe_text(e.__class__.__name__))
                time.sleep(_smart_retry_delay('timeout' if e.__class__.__name__ in ('ReadTimeout', 'ChunkedEncodingError') else 'connection', attempts))
                if '.ts' in url.lower() or '/hl' in url.lower() or '.mp4' in url.lower():
                    self.send_response(status)
                    self.send_header('Content-Type', media_type)
                    for k, v in response_headers.items():
                        if k.lower() == 'content-type':
                            continue
                        self.send_header(k, v)
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    if not head_only:
                        for chunk in (_stream_cache(client_ip, url) or []):
                            try:
                                self.wfile.write(chunk)
                            except Exception:
                                return
                    return
            finally:
                if response is not None and response.raw is not None and (head_only or attempts > 0):
                    try:
                        response.close()
                    except Exception:
                        pass

        self._send_json('{"detail": "Falha ao conectar após múltiplas tentativas"}', status=502)

    def _handle_tsdownloader(self, parsed, head_only=False):
        _dns_override()
        params = urllib.parse.parse_qs(parsed.query)
        url = params.get('url', [None])[0]
        if url:
            url = urllib.parse.unquote(url)
        if not url:
            self._send_json("{\"error\": \"Missing url parameter\"}", status=400)
            return

        original_headers = self._filtered_request_headers()
        stop_ts = [False]
        session = requests.Session()
        resolved_url = ['']
        last_status = [None]

        def _resolve_stream_url(force=False):
            if resolved_url[0] and not force:
                return resolved_url[0]
            host = _host_from_url(url)
            if host and not force:
                cached = _SESSION_CACHE['last_working_url'].get(host)
                if cached:
                    resolved_url[0] = cached
                    return resolved_url[0]
            probe_headers = _build_upstream_headers(original_headers, reconnects=0, response_code=last_status[0], prefer_stream=True, url=url)
            probe = session.get(url, headers=probe_headers, allow_redirects=True, stream=True, timeout=_timeout_tuple(url, prefer_stream=True))
            try:
                resolved_url[0] = probe.url or url
            finally:
                try:
                    probe.close()
                except Exception:
                    pass
            return resolved_url[0]

        def generate_ts():
            reconnects = 0
            while not stop_ts[0]:
                response = None
                try:
                    target_url = _resolve_stream_url(force=(reconnects > 0 and reconnects % 4 == 0))
                    _apply_origin_cooldown(target_url)
                    request_headers = _build_upstream_headers(original_headers, reconnects=reconnects, response_code=last_status[0], prefer_stream=True, url=target_url)
                    host = _host_from_url(target_url)
                    if not _host_is_available(host):
                        _host_backoff(host)
                    request_headers['User-Agent'] = _pick_user_agent(host, reconnects, prefer_stream=True)
                    response = session.get(target_url, headers=request_headers, stream=True, timeout=_timeout_tuple(target_url, prefer_stream=True), allow_redirects=True)
                    status_code = response.status_code
                    last_status[0] = status_code

                    ok_response, content_type = _validate_upstream_response(response, expect_stream=True, url=target_url)
                    if ok_response:
                        _mark_origin_ok(response.url or target_url)
                        _mark_host_ok(_host_from_url(response.url or target_url), final_url=(response.url or target_url), user_agent=request_headers.get('User-Agent'), content_type=content_type)
                        _remember_source_profile(response.url or target_url, _classify_source(response.url or target_url))
                        reconnects = 0
                        for chunk in response.iter_content(chunk_size=4096):
                            if stop_ts[0]:
                                _throttled_log('ts-stop-client', 60, logging.DEBUG, '[TS Downloader] Stream interrompido pelo cliente.')
                                return
                            if not chunk:
                                continue
                            yield chunk
                    elif status_code == 406:
                        reconnects += 1
                        _mark_origin_fail(response.url or target_url, code=406)
                        _mark_host_fail(_host_from_url(response.url or target_url), err='406', soft=True)
                        if reconnects <= 2:
                            _throttled_log('ts-406-soft:%s' % _origin_key(target_url), 60, logging.INFO, '[TS Downloader] 406 tratado como ruído transitório; retry silencioso.')
                        else:
                            _log_ts_status_once(status_code)
                        if reconnects >= 4:
                            resolved_url[0] = ''
                        time.sleep(_smart_retry_delay('406', reconnects))
                    elif status_code == 404:
                        reconnects += 1
                        _mark_origin_fail(response.url or target_url, code=404)
                        _mark_host_fail(_host_from_url(response.url or target_url), err='404')
                        _throttled_log('status:404:%s' % _origin_key(target_url), 20, logging.INFO if _source_profile(target_url) == 'xtream_bad' else logging.WARNING, '[TS Downloader] Origem respondeu 404; nova tentativa conservadora.')
                        resolved_url[0] = ''
                        time.sleep(_smart_retry_delay('connection', reconnects))
                    else:
                        reconnects += 1
                        _mark_origin_fail(response.url or target_url, code=status_code)
                        _mark_host_fail(_host_from_url(response.url or target_url), err=status_code)
                        _throttled_log('status:%s:%s' % (_origin_key(target_url), status_code), 20, logging.INFO if _source_profile(target_url) == 'xtream_bad' else logging.WARNING, '[TS Downloader] Resposta HTTP %s da origem.' % status_code)
                        if reconnects >= 3:
                            resolved_url[0] = ''
                        time.sleep(_smart_retry_delay('connection', reconnects))
                except (ReadTimeout, ChunkedEncodingError, ConnectionError) as e:
                    reconnects += 1
                    last_status[0] = e.__class__.__name__
                    _mark_origin_fail(resolved_url[0] or url, exc_name=e.__class__.__name__)
                    _mark_host_fail(_host_from_url(resolved_url[0] or url), err=e.__class__.__name__, soft=True)
                    resolved_url[0] = ''
                    if reconnects <= 2:
                        _throttled_log('ts-reconnect-net-soft:%s' % _origin_key(url), 12, logging.INFO, '[TS Downloader] Origem instável; reconectando sem drama (%s).' % _safe_text(e.__class__.__name__))
                    else:
                        _throttled_log('ts-reconnect-net-hard:%s' % _origin_key(url), 20, logging.INFO if _source_profile(url) == 'xtream_bad' else logging.WARNING, '[TS Downloader] Instabilidade persistente da origem; retry progressivo (%s).' % _safe_text(e.__class__.__name__))
                    time.sleep(_smart_retry_delay('timeout', reconnects))
                except GeneratorExit:
                    stop_ts[0] = True
                    return
                except Exception as e:
                    reconnects += 1
                    last_status[0] = e.__class__.__name__
                    msg = str(e).lower()
                    if 'broken pipe' in msg or 'connection reset' in msg:
                        stop_ts[0] = True
                        _throttled_log('ts-client-disconnect-exc', 60, logging.DEBUG, '[TS Downloader] Cliente desconectou durante o stream.')
                        return
                    _mark_origin_fail(resolved_url[0] or url, exc_name=e.__class__.__name__)
                    _mark_host_fail(_host_from_url(resolved_url[0] or url), err=e.__class__.__name__, soft=True)
                    resolved_url[0] = ''
                    _throttled_log('ts-stream-error:%s' % _origin_key(url), 15, logging.INFO if _source_profile(url) == 'xtream_bad' else logging.WARNING, '[TS Downloader] Erro no stream; reconectando com mínimo de interferência: %s' % _safe_text(e))
                    time.sleep(_smart_retry_delay('connection', reconnects))
                finally:
                    if response is not None:
                        try:
                            response.close()
                        except Exception:
                            pass
            _throttled_log('ts-stream-closed', 60, logging.DEBUG, '[TS Downloader] Stream encerrado pelo cliente.')

        self.send_response(200)
        self.send_header('Content-Type', 'video/mp2t')
        self.send_header('Connection', 'close')
        self.end_headers()
        if head_only:
            stop_ts[0] = True
            try:
                session.close()
            except Exception:
                pass
            return

        try:
            for chunk in generate_ts():
                try:
                    self.wfile.write(chunk)
                except Exception:
                    stop_ts[0] = True
                    _throttled_log('ts-client-disconnect-write', 60, logging.DEBUG, '[TS Downloader] Cliente desconectou durante a escrita do stream.')
                    return
        finally:
            stop_ts[0] = True
            try:
                session.close()
            except Exception:
                pass
            _throttled_log('ts-on-close', 120, logging.DEBUG, '[TS Downloader] Cliente encerrou a conexão local.')


def is_proxy_running():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.35)
    try:
        return s.connect_ex(('127.0.0.1', PORT)) == 0
    finally:
        try:
            s.close()
        except Exception:
            pass


def _server_run():
    global _SERVER
    try:
        _SERVER = _ThreadedHTTPServer(('127.0.0.1', PORT), _ProxyHandler)
        _SERVER.serve_forever(poll_interval=0.2)
    except Exception as e:
        _log('Falha ao iniciar proxy: %s' % e, level=xbmc.LOGERROR)


def start_proxy():
    global _SERVER_THREAD, _SERVER_STARTED
    if is_proxy_running():
        _SERVER_STARTED = True
        return True
    if _SERVER_THREAD and _SERVER_THREAD.is_alive():
        return True
    _SERVER_THREAD = threading.Thread(target=_server_run, name='OnePlayProxyServer', daemon=True)
    _SERVER_THREAD.start()
    for _ in range(30):
        if is_proxy_running():
            _SERVER_STARTED = True
            _log('Proxy nativo ativo na porta %d' % PORT)
            return True
        time.sleep(0.2)
    _log('Proxy nativo não respondeu na porta %d' % PORT, level=xbmc.LOGERROR)
    return False


def kodiproxy():
    return start_proxy()
