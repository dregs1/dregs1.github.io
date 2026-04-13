# -*- coding: utf-8 -*-
import socket
import struct
import random
import logging
import sys
import json
import time
import os
try:
    from kodi_six import xbmc, xbmcplugin, xbmcgui, xbmcaddon, xbmcvfs
except ImportError:
    import xbmc
    import xbmcplugin
    import xbmcgui
    import xbmcaddon
    import xbmcvfs
PY2 = sys.version_info[0] == 2
ADDON_ = xbmcaddon.Addon()
TRANSLATE_ = xbmc.translatePath if PY2 else xbmcvfs.translatePath
profile = TRANSLATE_(ADDON_.getAddonInfo('profile'))
if not os.path.exists(profile):
    os.makedirs(profile)
CACHE_FILE = os.path.join(profile, 'dns_cache.json')


_DNS_PATCH_STATE = {'installed': False, 'original_getaddrinfo': socket.getaddrinfo}


class customdns:
    def __init__(self, cache_file=CACHE_FILE, cache_ttl=3600):
        self.dns_server = [
            '94.140.14.140', # adguard
            '94.140.14.141', # adguard
            '208.67.222.222',# OpenDNS
            '208.67.220.220',# OpenDNS
            '1.1.1.1',       # Cloudflare
            '8.8.8.8'        # Google DNS
        ]
        self.original_getaddrinfo = _DNS_PATCH_STATE.get('original_getaddrinfo', socket.getaddrinfo)
        self.cache_file = cache_file
        self.cache_ttl = cache_ttl  # Tempo de expiração em segundos
        self.cache = self._load_cache()
        self.debug_mode = False
        self.mode_logger = False

        # Override DNS only once per runtime
        if not _DNS_PATCH_STATE.get('installed'):
            _DNS_PATCH_STATE['original_getaddrinfo'] = socket.getaddrinfo
            socket.getaddrinfo = self._resolver
            _DNS_PATCH_STATE['installed'] = True

    def _load_cache(self):
        """Carrega o cache do arquivo JSON, se existir"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache = json.load(f)
                    # Remove entradas expiradas
                    current_time = time.time()
                    return {
                        domain: data for domain, data in cache.items()
                        if data['expires'] > current_time
                    }
            return {}
        except Exception as e:
            logging.error("Erro ao carregar cache: {}".format(e))
            return {}

    def _save_cache(self):
        """Salva o cache no arquivo JSON"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logging.error("Erro ao salvar cache: {}".format(e))

    def is_valid_ipv4(self, ip):
        try:
            socket.inet_aton(ip)
            return True
        except socket.error:
            return False

    def is_valid_ipv6(self, ip):
        try:
            if hasattr(socket, 'inet_pton'):
                socket.inet_pton(socket.AF_INET6, ip)
                return True
            return False
        except socket.error:
            return False

    def _build_dns_query(self, domain):
        transaction_id = random.randint(0, 65535)
        flags = 0x0100
        questions = 1
        header = struct.pack('>HHHHHH', transaction_id, flags, questions, 0, 0, 0)

        if PY2:
            qname = b''.join(chr(len(part)) + part for part in domain.split('.')) + b'\x00'
        else:
            qname = b''.join(bytes([len(part)]) + part.encode() for part in domain.split('.')) + b'\x00'

        qtype = 1  # A record
        qclass = 1  # IN
        question = qname + struct.pack('>HH', qtype, qclass)
        return header + question

    def _parse_dns_response(self, data):
        answer_count = struct.unpack(">H", data[6:8])[0]
        offset = 12
        while data[offset] != 0:
            offset += 1
        offset += 5  # null + qtype + qclass

        for _ in range(answer_count):
            offset += 2  # name (pointer)
            rtype, rclass, ttl, rdlength = struct.unpack(">HHIH", data[offset:offset+10])
            offset += 10
            if rtype == 1 and rdlength == 4:  # A record
                ip_parts = struct.unpack(">BBBB", data[offset:offset+4])
                return ".".join(map(str, ip_parts))
            offset += rdlength
        return None

    def resolve(self, domain, dns_custom):
        # Verifica o cache
        if domain in self.cache:
            if self.cache[domain]['expires'] > time.time():
                if self.mode_logger:
                    logging.info("Cache hit for {}: {}".format(domain, self.cache[domain]['ip']))
                return self.cache[domain]['ip']
            else:
                # Remove entrada expirada
                del self.cache[domain]
                self._save_cache()

        try:
            domain_clean = domain.strip('.')
            if self.mode_logger:
                logging.debug("Resolvendo {} via DNS {}".format(domain_clean, dns_custom))

            query = self._build_dns_query(domain_clean)

            if self.is_valid_ipv6(dns_custom):
                s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
                addr = (dns_custom, 53, 0, 0)
            else:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                addr = (dns_custom, 53)

            s.settimeout(3)
            s.sendto(query, addr)
            data, _ = s.recvfrom(512)
            s.close()

            ip = self._parse_dns_response(data)
            if ip:
                # Salva no cache com timestamp de expiração
                self.cache[domain] = {
                    'ip': ip,
                    'expires': time.time() + self.cache_ttl
                }
                self._save_cache()
                if self.mode_logger:
                    logging.debug("Resolved {} to {}".format(domain, ip))
                return ip
        except Exception as e:
            if self.mode_logger:
                logging.error("Erro ao resolver {} com {}: {}".format(domain, dns_custom, e))
        return None

    def _resolver(self, host, port, *args, **kwargs):
        try:
            if self.is_valid_ipv4(host) or self.is_valid_ipv6(host):
                if self.mode_logger:
                    logging.debug("Bypass: {} já é IP".format(host))
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (host, port))]
            for dns_server in self.dns_server:
                ip = self.resolve(host, dns_server)
                if ip:
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port))]

            if self.mode_logger:
                logging.warning("Falha ao resolver {}, fallback para getaddrinfo".format(host))
        except Exception as e:
            if self.mode_logger:
                logging.error("Erro no resolver para {}: {}".format(host, e))

        return self.original_getaddrinfo(host, port, *args, **kwargs)


