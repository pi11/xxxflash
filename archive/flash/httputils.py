# -*- coding: utf-8 -*-
# Реализация API memori.ru
# добавление закладки (букмарк) 
#
# Copyright (c) 2010, WebII Lab (webii.ru)
# All rights reserved.
#

def memorize(username, password, description, href, extended, tags, point=5, share="yes", show="yes", start="yes"):
    """
    Сохраняет урл в закладках на memori.ru
    параметры: 
    --------
    username - имя пользователя на memori.ru
    password - пароль на memori.ru
    description - описание зауладки
    href - ссылка
    extended - подробное описание закладки
    tags - список тэгов через запятую
    point - оценка (от 1 до 5)
    share - по умолчанию yes - закладка публичная  (no - нет)
    show - по умолчанию yes - видна друзьям (no - нет)
    start - по умолчанию yes - показывать на главной  (no - нет)
    """
    from urllib import urlencode
    import urllib2
    from urllib2 import Request, urlopen, URLError, HTTPError
    ourl = 'http://memori.ru/api-v2/posts/add?'
    params=urlencode({'description':description.encode("utf-8"), 'href':href, 'extended':extended.encode("utf-8"), 'tags':tags.encode("utf-8"),
                      'point':point, 'share':share, 'show':show, 'start':start} )
    theurl = ourl+params
    passman = urllib2.HTTPPasswordMgrWithDefaultRealm()    
    passman.add_password(None, ourl, username, password)   
    authhandler = urllib2.HTTPBasicAuthHandler(passman)   
    opener = urllib2.build_opener(authhandler)
    try:
        urlh = opener.open(theurl)
        data = urlh.read()
    except Exception, e:
        return False
    urlh.close()
    return str(data)
    
def bookmark(username, password, url, description, tags, status=0):
    """
    Добавляет ссылку в b.b000.ru
    """
    import sys
    from urllib import urlencode
    import urllib2
    from urllib2 import Request, urlopen, URLError, HTTPError
    ourl = 'http://b.b000.ru/api_add.php?'
    params=urlencode({'username':username, 'password':password, 'description':description.encode("utf-8"),
                      'url':url, 'tags':tags.encode("utf-8"), 'status':status} )
    theurl = ourl+params
    #print theurl
    opener = urllib2.build_opener()
    try:
        urlh = opener.open(theurl)
        data=urlh.read()
    except Exception, e:
        #print sys.exc_info()
        return False
    urlh.close()
    return True
