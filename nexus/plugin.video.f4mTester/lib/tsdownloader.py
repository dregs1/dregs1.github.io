# -*- coding: utf-8 -*-
import socket
import threading
import six
if six.PY3:
    from urllib.parse import urlparse, parse_qs, quote, unquote, unquote_plus
else:
    from urlparse import urlparse, parse_qs
    from urllib import quote, unquote, unquote_plus
import os
import re
import requests
import logging
import base64
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_local_ip():
    try:
        # Cria um socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        local_ip = s.getsockname()[0]
    except Exception as e:
        local_ip = '127.0.0.1'
    finally:
        try:
            s.close()
        except:
            pass
    return local_ip

def log(msg):
    try: 
        logger.info(msg)    
    except:
        pass

#HOST_NAME = '127.0.0.1'
HOST_NAME = get_local_ip()
PORT_NUMBER = 58550

url_proxy = 'http://'+HOST_NAME+':'+str(PORT_NUMBER)+'/?url='


global HEADERS_BASE
global STOP_SERVER
HEADERS_BASE = {}
STOP_SERVER = False


class XtreamCodes:
    def set_headers(self,url):
        global URL_BASE
        global HEADERS_BASE        
        headers_default = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0', 'Connection': 'keep-alive'}
        #headers_default = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0'}
        headers = {}
        if 'User-Agent' in url:
            try:
                user_agent = url.split('User-Agent=')[1]
                try:
                    user_agent = user_agent.split('&')[0]
                except:
                    pass
                try:
                    user_agent = unquote_plus(user_agent)
                except:
                    pass
                try:
                    user_agent = unquote(user_agent)
                except:
                    pass
                if 'Mozilla' in user_agent:
                    headers['User-Agent'] = user_agent
            except:
                pass
        if 'Referer' in url:
            try:
                referer = url.split('Referer=')[1]
                try:
                    referer = referer.split('&')[0]
                except:
                    pass
                try:
                    referer = unquote_plus(referer)
                except:
                    pass
                try:
                    referer = unquote(referer)
                except:
                    pass                
                headers['Referer'] = referer
            except:
                pass
        if 'Origin' in url:
            try:
                origin = url.split('Origin=')[1]
                try:
                    origin = origin.split('&')[0]
                except:
                    pass
                try:
                    origin = unquote_plus(origin)
                except:
                    pass
                try:
                    origin = unquote(origin)
                except:
                    pass                
                headers['Origin'] = origin
            except:
                pass
        #HEADERS_ = headers if headers else headers_default
        if headers != {}:
            headers.update({'Connection': 'keep-alive'})
            HEADERS_ = headers
        else:
            HEADERS_ = headers_default
        if HEADERS_BASE == {}:
            HEADERS_BASE = HEADERS_

    def send_ts(self,self_server,url):
        global HEADERS_BASE
        if url:
            self_server.send_header('Content-type','video/mp2t')
            self_server.end_headers() 
            # try:
            #     r = requests.get(url, headers=HEADERS_BASE, allow_redirects=True, stream=True, verify=False, timeout=4)
            #     url = r.url
            # except:
            #     pass
            try:
                for i in range(10):
                    count = i + 1
                    stop_user = False
                    r = requests.get(url, headers=HEADERS_BASE, allow_redirects=True, stream=True, verify=False)
                    code = r.status_code
                    log('Status Code: %s'%str(code))
                    if code == 200:                    
                        try:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:                      
                                    try:
                                        self_server.conn.sendall(chunk)
                                    except:
                                        stop_user = True
                                        break
                        except:
                            pass
                    else:
                        if stop_user:
                            break
                        elif count == 7:
                            break

            except:
                pass

    def parse_url(self,url):
        parsed_url = urlparse(url)
        scheme = parsed_url.scheme
        host = parsed_url.hostname
        port = parsed_url.port
    
        return scheme, host, port    



class ProxyHandler(XtreamCodes):
    def __init__(self, conn, addr, server):
        self.conn = conn
        self.addr = addr
        self.server = server
        self.path = ""
        self.request_method = ""

    def parse_request(self, request):
        parts = request.split(b' ')
        self.request_method = parts[0].decode()

    def parse_request2(self, request):
        parts = request.split(b' ')
        if len(parts) >= 2:
            self.path = parts[1].decode()

    def send_response(self, code, message=None):
        response = "HTTP/1.1 {} {}\r\n".format(code, message if message else "")
        self.conn.sendall(response.encode())

    def send_header(self, keyword, value):
        header = "{}: {}\r\n".format(keyword, value)
        self.conn.sendall(header.encode())

    def end_headers(self):
        self.conn.sendall(b"\r\n")

    def extract_header(self, request_data, header_name):
        header_lines = request_data.split(b'\r\n')
        for line in header_lines:
            if header_name in line:
                return line
        return None        

    def get_range(self, request_data, content_length):
        range_header = self.extract_header(request_data, b'Range:')
        if range_header:
            parts = range_header.split(b"-")
            start = int(parts[0].split(b'=')[-1])
            end = int(parts[1]) if parts[1] else content_length - 1
            return start, end
        else:
            return 0, content_length - 1       

    def stream_video(self, video_url, request_data):
        try:
            video_url = video_url.split('|')[0]
        except:
            pass
        try:
            video_url = video_url.split('%7C')[0]
        except:
            pass
        global HEADERS_BASE
        headers = HEADERS_BASE
        try:
            response = requests.head(video_url, headers=headers)
            if response.status_code == 200:
                content_length = int(response.headers.get('Content-Length', 0))
                start, end = self.get_range(request_data, content_length)
                #headers['Range'] = f'bytes={start}-{end}'  # Adicionando cabeçalho de intervalo
                headers['Range'] = 'bytes=%s-%s'%(str(start),str(end))  # Adicionando cabeçalho de intervalo
                response = requests.get(video_url, headers=headers, stream=True)
                if response.status_code == 206 or response.status_code == 200:
                    self.send_partial_response(206, response.headers, content_length, response.iter_content(chunk_size=1024), start, end)
                else:
                    self.send_response(404)
            else:
                self.send_response(404)
        except Exception as e:
            #print("Error streaming video:", e)
            self.send_response(500)

    def send_partial_response(self, status_code, headers, content_length, content_generator, start, end):
        self.send_response(status_code)
        #self.send_header('Content-type','video/mp4')
        self.send_header("Accept-Ranges", "bytes")
        if start is not None:
            #self.send_header("Content-Range", f"bytes {start}-{end}/{content_length}")
            self.send_header("Content-Range", "bytes %s-%s/%s"%(str(start),str(end),str(content_length)))
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()

        for chunk in content_generator:
            if STOP_SERVER:
                break
            try:
                self.conn.sendall(chunk)
            except:
                pass
                        

    def handle_request(self):
        global HEADERS_BASE
        global STOP_SERVER    
        request_data = self.conn.recv(1024)
        self.parse_request(request_data)
        self.parse_request2(request_data)
        if self.request_method == 'HEAD':
            self.send_response(200) # envia status 200 sempre
            pass
        elif self.path == "/stop":
            self.send_response(200) # envia status 200 sempre
            STOP_SERVER = True
            HEADERS_BASE = {}          
            self.server.stop_server()
        elif self.path == "/reset":
            self.send_response(200) # envia status 200 sempre
            HEADERS_BASE = {}
        elif self.path == '/check':
            self.send_response(200) # envia status 200 sempre
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.conn.sendall(b"Hello, world!")
        else:
            url_path = unquote_plus(self.path)
            try:
                url_path = url_path.replace('VIDEO_TS.IFO', '')
            except:
                pass
            self.set_headers(url_path)
            url_parts = urlparse(url_path)
            query_params = parse_qs(url_parts.query)
            if 'url' in query_params:
                url = url_path.split('url=')[1]
                try:
                    url = base64.b64decode(url).decode('utf-8')
                except:
                    pass
                try:
                    url = url.split('|')[0]
                except:
                    pass
                try:
                    url = url.split('%7C')[0]
                except:
                    pass
            else:
                url = url_path
            # XTREAM CODES
            if '.mp4' in url and not '.m3u8' in url and not '.ts' in url:
                self.stream_video(url, request_data)                    
            elif '.ts' in url:
                self.send_response(200) # envia status 200 sempre
                self.send_ts(self,url)
            elif not '.m3u8' in url and not '.ts' in url and not '.mp3' in url and not '.rmv' in url and not '.rmvb' in url and not 'm3u8' in url:
                self.send_response(200) # envia status 200 sempre
                self.send_ts(self,url)
        self.conn.close()  # Fechar o socket de conexão após enviar a resposta

def monitor():
    try:
        try:
            from kodi_six import xbmc
        except:
            import xbmc
        monitor = xbmc.Monitor()
        while not monitor.waitForAbort(3):
            pass
        #log('Ecerrando proxy server')
        url = 'http://'+HOST_NAME+':'+str(PORT_NUMBER)+'/stop'
        try:
            r = requests.get(url,timeout=4)
        except:
            pass
        #log('Proxy encerrado')
        try:
            os._exit(1)
        except:
            pass
    except:
        pass 

class Server:
    def __init__(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((HOST_NAME, PORT_NUMBER))
        self.server_socket.listen(10)

    def serve_forever(self):
        global STOP_SERVER
        while True:
            if STOP_SERVER:
                break
            conn, addr = self.server_socket.accept()
            handler = ProxyHandler(conn, addr, self)
            threading.Thread(target=handler.handle_request).start()

    def stop_server(self):
        self.server_socket.close()

def loop_server():
    server = Server()
    server.serve_forever()

class XtreamProxy:
    def reset(self):
        try:
            url = 'http://'+HOST_NAME+':'+str(PORT_NUMBER)+'/reset'
            r = requests.get(url,timeout=3)
        except:
            pass

    def check_service(self):
        try:
            url = 'http://'+HOST_NAME+':'+str(PORT_NUMBER)+'/check'
            r = requests.head(url,timeout=3)
            if r.status_code == 200:
                return True
            return False
        except:
            return False

    def start(self):
        status = self.check_service()
        if status == False:
            proxy_service = threading.Thread(target=loop_server).start()
            monitor_service = threading.Thread(target=monitor).start()
        else:
            self.reset()

# print('url proxy: ',url_proxy)
# XtreamProxy().start()

