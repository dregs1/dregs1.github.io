# -*- coding: utf-8 -*-
from lib.helper import *
from lib import hlsretry, tsdownloader


def m3u8_to_ts(url):
    if '.m3u8' in url and '/live/' in url and int(url.count("/")) > 5:
        url = url.replace('/live', '').replace('.m3u8', '')
    return url


def basename(p):
    """Returns the final component of a pathname"""
    i = p.rfind('/') + 1
    return p[i:]
    
def convert_to_m3u8(url):
    if '|' in url:
        url = url.split('|')[0]
    elif '%7C' in url:
        url = url.split('%7C')[0]
    if not '.m3u8' in url and not '/hl' in url and int(url.count("/")) > 4 and not '.mp4' in url and not '.avi' in url:
        parsed_url = urlparse(url)
        try:
            host_part1 = '%s://%s'%(parsed_url.scheme,parsed_url.netloc)
            host_part2 = url.split(host_part1)[1]
            url = host_part1 + '/live' + host_part2
            file = basename(url)
            if '.ts' in file:
                file_new = file.replace('.ts', '.m3u8')
                url = url.replace(file, file_new)
            else:
                url = url + '.m3u8'
                # file_new = file + '.m3u8'
                # new_url = url.replace(file, file_new)
        except:
            pass
    return url 

def player_hlsretry(name,url,iconimage,description):
    if name:
        name = 'F4MTESTER - HLSRETRY - ' + name
    else:
        name = 'F4MTESTER - HLSRETRY'
    url = unquote_plus(url)
    url = 'http://%s:%s/?url=%s'%(str(hlsretry.HOST_NAME),str(hlsretry.PORT_NUMBER),quote(url))
    hlsretry.XtreamProxy().start()
    li=xbmcgui.ListItem(name)
    iconimage = iconimage if iconimage else ''
    li.setArt({"icon": "DefaultVideo.png", "thumb": iconimage})
    if kversion > 19:
        info = li.getVideoInfoTag()
        info.setTitle(name)
        info.setPlot(description)
    else:
        li.setInfo(type="Video", infoLabels={"Title": name, "Plot": description})
    xbmc.Player().play(item=url, listitem=li)

def player_tsdownloader(name,url,iconimage,description):
    if name:
        name = 'F4MTESTER - TSDOWNLOADER - ' + name
    else:
        name = 'F4MTESTER - TSDOWNLOADER'
    url = unquote_plus(url)
    url = url.replace('live/', '').replace('.m3u8', '')
    url = 'http://%s:%s/?url=%s'%(str(tsdownloader.HOST_NAME),str(tsdownloader.PORT_NUMBER),quote(url))
    tsdownloader.XtreamProxy().start() 
    li=xbmcgui.ListItem(name)
    iconimage = iconimage if iconimage else ''
    li.setArt({"icon": "DefaultVideo.png", "thumb": iconimage})
    if kversion > 19:
        info = li.getVideoInfoTag()
        info.setTitle(name)
        info.setPlot(description)
    else:
        li.setInfo(type="Video", infoLabels={"Title": name, "Plot": description})
    xbmc.Player().play(item=url, listitem=li)           



def player_input(name,url,iconimage,description):    
    if name:
        name = 'F4MTESTER - INPUTSTREAM ADAPTIVE - ' + name
    else:
        name = 'F4MTESTER - INPUTSTREAM ADAPTIVE'    
    if not '.mp4' in url and not '.mp3' in url and not '.mkv' in url and not '.avi' in url and not '.rmvb' in url:
        url = convert_to_m3u8(url)
        if '.m3u8' in url:
            import inputstreamhelper
            is_helper = inputstreamhelper.Helper("hls")
            if is_helper.check_inputstream():
                url = unquote_plus(url)
                if '|' in url:
                    header = url.split('|')[1]
                else:
                    header = 'User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0'
                play_item = xbmcgui.ListItem(path=url)
                play_item.setArt({"icon": "DefaultVideo.png", "thumb": iconimage})
                if kversion > 19:
                    info = play_item.getVideoInfoTag()
                    info.setTitle(name)
                    info.setPlot(description)
                else:
                    play_item.setInfo(type="Video", infoLabels={"Title": name, "Plot": description})                  
                play_item.setContentLookup(False)
                play_item.setMimeType("application/vnd.apple.mpegurl")
                if kversion >= 19:
                    play_item.setProperty('inputstream', is_helper.inputstream_addon)
                else:
                    play_item.setProperty('inputstreamaddon', is_helper.inputstream_addon)                  
                play_item.setProperty("inputstream.adaptive.manifest_type", "hls")
                if '|' in url:
                    play_item.setProperty("inputstream.adaptive.manifest_headers", header)
                #play_item.setProperty('inputstream.adaptive.manifest_update_parameter', 'full')
                #play_item.setProperty('inputstream.adaptive.is_realtime_stream', 'true')   
                xbmc.Player().play(item=url, listitem=play_item)
        else:
            notify('O link não é M3U8')                                     
    else:
        notify('Formato invalido!')


    


#### run addon ####
def run(params):
    stream_type = params.get('streamtype', None)
    iconimage = params.get('iconImage', params.get('thumbnailImage', addonIcon))
    name = params.get('name', 'F4mTester')
    url = params.get('url', '')
    description = params.get('description', '')
    if not stream_type:
        dialog('F4MTESTER PLAYER')
    elif stream_type !=None:
        if url:
            op = select('SELECT PLAYER', ['PROXY - HLSRETRY', 'PROXY - TSDOWNLOADER', 'INPUTSTREAM ADAPTATIVE'])
            if op == 0:
                player_hlsretry(name,url,iconimage,description)
            elif op == 1:
                player_tsdownloader(name,url,iconimage,description)
            elif op == 2:
                player_input(name,url,iconimage,description)
                

