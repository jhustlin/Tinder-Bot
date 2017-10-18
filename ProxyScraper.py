from threading import Thread
import urllib2
import re
import time
import datetime

import lxml.html as html


def replaceme(source):
    xpathsource = html.fromstring(source)
    for styleinfo in xpathsource.xpath('//style/text()'):
        stylelines = styleinfo.split("\n")

        for styleline in stylelines:
            matchObj = re.match(r"\.(.*?){(.*?)}", styleline)
            if matchObj:
                classname = 'class="' + matchObj.group(1) + '"'
                styleattr = 'style="' + matchObj.group(2) + '"'
                source = source.replace(classname, styleattr)

    return source


def hidemyass(url):
    source = urllib2.urlopen(url).read()
    source = html.fromstring(replaceme(source))
    list = []
    for tr in source.xpath('//tr'):
        array = tr.xpath("td[2]//*[not(contains(@style,'display:none'))]/text() | td[3]/text()")

        String = '.'.join(array)
        bla = re.sub(r"\.+", '.', re.sub(r"\.\n", ":", String))
        findip = re.findall(r'(([0-9]+(?:\.[0-9]+){3}))+(.*)', bla)

        if (len(findip)):
            ip = ''.join(findip[0][1] + findip[0][2])
            list.append([ip])
    return list


class ProxyHandler:
    valid_proxies = []
    accounts = {}

    def __init__(self, use_random_proxies=False):
        length = len(open('Proxies').readlines())
        proxies = hidemyass("http://proxylist.hidemyass.com/search-1317321#listable") if use_random_proxies else \
            [x[:-1] for x in open('Proxies')][:100 if length > 100 else length]
        print proxies
        for prox in proxies:
            Thread(target=self.check_proxy, args=(prox,)).start()
        while not len(self.valid_proxies):
            time.sleep(.1)

    def is_valid_proxy(self, prox):
        try:
            proxy_handler = urllib2.ProxyHandler({'https': prox})
            opener = urllib2.build_opener(proxy_handler)
            opener.addheaders = [('User-agent', 'Mozilla/5.0')]
            urllib2.install_opener(opener)
            req = urllib2.Request('https://www.google.com/')  # change the URL to test here
            urllib2.urlopen(req, timeout=3)
            return True
        except urllib2.HTTPError:
            return False
        except Exception:
            return False

    def check_proxy(self, prox=None, user=None):
        if user is None:
            website = self.is_valid_proxy(prox)
            if website:
                self.valid_proxies.append([prox, time.time()])
        else:
            website = self.is_valid_proxy(prox)
            if not website:
                self.accounts[user] = self.valid_proxies.pop()

    def update_accounts(self):
        for user, address in [[user, proxy] for user, proxy, update_time in self.accounts.iteritems() if
                              update_time + datetime.timedelta(minutes=5) > time.time()]:
            Thread(target=self.check_proxy, args=(address,)).start()


    def get_proxy(self, username):
        if username in self.accounts.keys():
            Thread(target=self.check_proxy, args=(username,)).start()
            return self.accounts[username][0]
        else:
            if len(self.valid_proxies):
                self.accounts[username] = self.valid_proxies.pop()
                return self.accounts[username][0]
            else:
                print 'Ran out of proxies!'
                time.sleep(5)
                return self.get_proxy(username)
    @staticmethod
    def format(proxy):
        return {'https': proxy}


if __name__ == '__main__':
    p = ProxyHandler()
    for x in xrange(50):
        print p.get_proxy('asdfasdf' + str(x))
