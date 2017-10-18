import os
from sys import stdout
import sqlite3
import traceback
import datetime
from Queue import Queue
from threading import Thread
import time

import exrex
import requests
from requests.exceptions import ProxyError, ConnectionError

from ConfigHandler import get_details
import FacebookAuth
from ProxyScraper import ProxyHandler
import TwilioManager






# region Static Variables
URL = 'https://api.gotinder.com'
accounts = []

HEADERS = {'Accept-Language': 'en-GB;q=1, en;q=0.9, fr;q=0.8, de;q=0.7, ja;q=0.6, nl;q=0.5',
           'User-Agent': 'Tinder/3.0.4 (iPhone; iOS 7.1; Scale/2.00)',
           'os_version': '70000000006', 'Accept': '*/*', 'platform': 'ios', 'Connection': 'keep-alive',
           'Proxy-Connection': 'keep-alive', 'app_version': '1', 'Accept-Encoding': 'gzip, deflate'}


class TinderErrorAuthenticating(Exception):
    pass


# endregion



# region Threading
class Worker(Thread):
    """Thread executing tasks from a given tasks queue"""

    def __init__(self, tasks):
        Thread.__init__(self)
        self.tasks = tasks
        self.daemon = False
        self.start()

    def run(self):
        while True:
            func, args, kargs = self.tasks.get()
            try:
                func(*args, **kargs)
            except:
                print traceback.format_exc()
            finally:
                self.tasks.task_done()


class ThreadPool:
    """Pool of threads consuming tasks from a queue"""

    def __init__(self, num_threads):
        self.tasks = Queue(num_threads)
        for _ in range(num_threads): Worker(self.tasks)

    def add_task(self, func, *args, **kargs):
        """Add a task to the queue"""
        self.tasks.put((func, args, kargs))

    def wait_completion(self):
        """Wait for completion of all the tasks in the queue"""
        self.tasks.join()


# endregion

class CustomRequest:
    def __init__(self, username, use_proxy=True):
        self.HEADERS = HEADERS
        self.username = username
        self.use_proxy = use_proxy
        try:
            if 'proxy' not in globals():
                globals()['proxy'] = ProxyHandler()
        except:
            print traceback.format_exc()

    def __req(self, method, *args, **kwargs):
        try:
            j = requests.request(method,
                                 proxies=proxy.format(proxy.get_proxy(self.username)) if self.use_proxy else None,
                                 *args, **kwargs)
            if j.status_code == 403:
                return self.__req(method, *args, **kwargs)
            return j.json()
        except (ValueError, ConnectionError):
            return self.__req(method,*args,**kwargs)
        except ProxyError:
            if 'like' in args[0]:
                return
            else:
                return self.__req(method,*args,**kwargs)
        except Exception as e:
            print traceback.format_exc()
            return self.__req(method, *args, **kwargs)

    def auth(self, token):
        req = self.__req('POST', URL + '/auth', data={"facebook_token": token})
        if 'token' in req.keys():
            self.HEADERS['X-Auth-Token'] = req['token']
        return req

    def post(self, *args, **kwargs):
        return self.__req('POST', headers=HEADERS, *args, **kwargs)

    def get(self, *args, **kwargs):
        return self.__req('GET', headers=HEADERS, *args, **kwargs)


# region Clients
class BaseClient:
    def __init__(self, token, username, location=None, use_proxy=True):
        self.token = token
        self.requests = CustomRequest(username, use_proxy)
        r = self.requests.auth(token)
        if r is None or 'code' in r.keys():
            self.banned = True
            raise TinderErrorAuthenticating('Banned')
        else:
            self.banned = False
            self.user = r['user']
            self.id = r['user']['_id']
            self.location = location


    def updateLocation(self):
        return self.requests.post(URL + '/user/ping', data=self.location)


    def likeUser(self, id):
        if self.requests.get(URL + '/like/' + id) is None:
            self.storeData.status[self.token]['liked'] -= 1


    def getRecs(self):
        return self.requests.post(URL + '/user/recs', data={"limit": 40})


    def getUpdate(self, date='2014-04-07T06:36:49.027Z'):
        return self.requests.post(URL + '/updates', data={'last_activity_date': date})


    def sendMessage(self, message, matchid):
        req = self.requests.post(URL + '/user/matches/' + matchid, data={"message": message})
        if 'from' in req.keys():
            self.storeData.status[self.token]['Messages Sent'] += 1


    def phoneResquest(self, number):
        return self.requests.post(URL + '/sendtoken', data={'phone_number': number})


    def validate(self, token):
        return self.requests.post(URL + '/validate', data={'token': token})


    def updateProfile(self):
        return self.requests.post(URL + '/user/profile/',
                                  data={'distance_filter': 120, 'gender': self.user['gender'], 'age_filter_max': 90,
                                        'age_filter_min': 18,
                                        'gender_filter': self.user['gender_filter']})


class MainClient(BaseClient):
    def __init__(self, token, username, location=None, data=None,
                 regexMessage=r"(hello|hey|hi) (you are|you're|ur) (cute|handsome|sexy) (we should|we can|can we) (talk|im each other|communicate) (chat|instant message|IM) (each other|one another|with each other) http://82\.221\.105\.183/uk and my (sn|username|profile name) is (myjaan|martha|SexyKissing21) (l8r|ciao|later)"):
        BaseClient.__init__(self, token, location=location, username=username)
        self.regexMessage = regexMessage
        self.storeData = data
        self.storeData.status[token] = {'liked': 0, 'status': 'Running', 'Matched': 0, 'Messages Sent': 0}
        self.token = token
        self.continueRunning = True

    def likeUsers(self, numusers):
        self.continueRunning = True
        self.likedUsers = 0
        while self.likedUsers < numusers and self.continueRunning:
            pool.add_task(self.likeBatch)
            time.sleep(len(accounts) * LikePauseInSeconds)


    def processUser(self, user):
        parameters = ['name', 'gender', 'birth_date', 'bio', '_id']
        values = [user[x] for x in parameters]
        photos = [','.join([x['url'] for x in user['photos'] if 'url' in x.keys()])]
        return values + photos

    def likeBatch(self, recs=None):
        try:
            if recs is None:
                recs = self.getRecs()['results']

                if self.continueRunning:
                    self.storeData.status[self.token]['status'] = 'Running'
        except KeyError:
            if 'exhausted' in str(recs):
                self.storeData.status[self.token]['status'] = 'Exhausted'
            elif 'timeout' in str(recs):
                self.storeData.status[self.token]['status'] = 'Timeout'
            return
        for user in recs:
            self.storeData.userDataList.append(self.processUser(user))
            pool.add_task(self.likeUser, user['_id'])
            self.likedUsers += 1
            self.storeData.status[self.token]['liked'] += 1

    def manual_phone_authentication(self, number):
        authenticated = 'user is already validated' in self.phoneResquest('1')
        if authenticated:
            return True
        print self.phoneResquest(number)
        return 'True' in str(self.validate(input('Please enter token:')))

    def get_message(self, number):
        start_time = time.time()
        response = TwilioManager.get_messages(number)
        while response is None and start_time + datetime.timedelta(minutes=1).total_seconds() > time.time():
            response = TwilioManager.get_messages(number)
        return response

    def get_number(self):
        return TwilioManager.purchase_number()

    def authenticate(self, number=None):
        if 'user is already validated' in self.phoneResquest('1'):
            return 'Already authenticated'
        if number is None:
            number = self.get_number()
        print 'Number is ', number
        if number is not None:
            request = self.phoneResquest(number)
            if request['status'] == 500:
                return 'INVALID NUMBER', number, request
            elif request['status'] != 200:
                return 'INVALID STATUS FOUND: ' + str(request)
            response = self.get_message(number)
            print response
            if response is not None:
                parsed = response.split(':')[1].strip()
                return (self.validate(parsed), 'auth')

    def getNumberOfLikedUsers(self, update):
        return len(update['matches'])

    def getNumberUnMessagedUsers(self, update):
        return len(
            [user for user in update['matches'] if not any([x for x in user['messages'] if x['from'] == self.id])])


    def getNumberOfMessagesSent(self, update):
        return self.getNumberOfLikedUsers(update) - self.getNumberUnMessagedUsers(update)

    def displayReport(self, update=None):
        if update is None:
            update = self.getUpdate()
        self.storeData.status[self.token]['Matched'] = self.getNumberOfLikedUsers(update)
        self.storeData.status[self.token]['Messages Sent'] = self.getNumberOfMessagesSent(update)
        if self.storeData.status[self.token]['Matched'] - self.storeData.status[self.token][
            'Messages Sent'] > MatchesToMessageAmount:
            print 'Liking all users...'
            for _ in range(3):
                self.messageNewAllUsers(update)


    def messageNewAllUsers(self, matches=None):
        try:
            if matches is None:
                matches = self.getUpdate()
            print 'Found matches'
            self.storeData.status[self.token]['Matched'] = self.getNumberOfLikedUsers(matches)
            self.storeData.status[self.token]['Messages Sent'] = self.getNumberOfMessagesSent(matches)
            try:
                recs = matches['matches']
            except KeyError:
                return
            print 'Recs successful...matching..'
            for user in recs:
                if not any([x for x in user['messages'] if x['from'] == self.id]):
                    pool.add_task(self.sendMessage, exrex.getone(self.regexMessage), user['_id'])
                    time.sleep(len(accounts) * .1)
        except ValueError:
            self.messageNewAllUsers()

    def start_main_loop(self):
        pool.add_task(self.main_loop)


    def main_loop(self):
        print 'Starting...'
        self.storeData.status[self.token]['start'] = time.time()
        while True:
            try:
                self.updateLocation()
                pool.add_task(self.displayReport)
                self.likeUsers(CheckForMatchedUsersEveryXLikes)
                time.sleep(TimeoutPauseInSeconds if self.storeData.status[self.token][
                                                        'status'] == 'Timeout' else PauseInSeconds)
                print 'Restarting'
            except:
                print traceback.format_exc()


# endregion

# region DB
class DataStore():
    storedUsers = 0
    userDataList = []
    status = {}
    matched = 0
    messages_sent = 0
    matches_to_go = 0
    running = True

    def __init__(self):
        pool.add_task(self.storeData)


    def storeData(self):
        con = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + '/data.db')
        c = con.cursor()
        last_time = time.time()
        while self.running:
            users = self.userDataList
            self.userDataList = []
            if users:
                c.executemany('INSERT  OR IGNORE INTO Data VALUES (?,?,?,?,?,?)', users)
                con.commit()
                self.storedUsers += c.rowcount
            if time.time() > last_time + datetime.timedelta(seconds=2).total_seconds():
                current_stats = {}
                temp_stats = [self.status[x] for x in self.status.keys()]
                current_stats['Stored'] = self.storedUsers
                current_stats['Liked'] = sum([x['liked'] for x in temp_stats])
                current_stats['Matched'] = sum([x['Matched'] for x in temp_stats])
                current_stats['Messages Sent'] = sum([x['Messages Sent'] for x in temp_stats])
                current_stats['Running'] = len([x for x in temp_stats if x['status'] == 'Running'])
                current_stats['Exhausted'] = len([x for x in temp_stats if x['status'] == 'Exhausted'])
                current_stats['Timedout'] = len([x for x in temp_stats if x['status'] == 'Timeout'])
                try:
                    current_stats['LPS'] = sum([x['liked'] for x in temp_stats]) / (time.time() - start_time)
                except (ZeroDivisionError, KeyError):
                    pass
                stdout.write(
                    '[' + ']['.join(
                        [': '.join([str(x), str(current_stats[x])]) for x in current_stats.keys()]) + ']\r')
                last_time = time.time()
            time.sleep(.1)
# endregion


# region Loops
def loop(temp_location=None):

    data = DataStore()
    print len(FacebookAuth.get_all_valid_accounts())

    for username, token, location, refresh in FacebookAuth.get_all_valid_accounts():
        print refresh
        lat, lon = temp_location if temp_location is not None else location
        profile = MainClient(token, location={u'lat': lat, u'lon': lon}, data=data, username=username)
        if not profile.banned:
            profile.updateProfile()
            profile.start_main_loop()
            accounts.append(profile)
        else:
            FacebookAuth.update_accounts()
        time.sleep(5)


def auth(temp_location=None):
    data = DataStore()
    for token, location, username in FacebookAuth.get_all_unauth_accounts()[:len(temp_location)]:
        lat, lon = temp_location[len(accounts)] if temp_location is not None else location
        print '[' + (']['.join([token, str(lat), str(lon), username])) + ']'
        if temp_location is not None:
            FacebookAuth.set_location(username, lat, lon)
        profile = MainClient(token, location={u'lat': lat, u'lon': lon}, data=data, username=username)
        auth_response = profile.authenticate()
        print auth_response
        profile.updateProfile()
        profile.start_main_loop()
        accounts.append(profile)
    print 'Finished'
    FacebookAuth.update_accounts()

# endregion

if __name__ == "__main__":
    # region Config Variables
    proxy = ProxyHandler()
    config = get_details()
    Threads = int(config['Threads'])
    CheckForMatchedUsersEveryXLikes = int(config['CheckForMatchedUsersEveryXLikes'])
    AmountOfLikesPerPause = int(config['AmountOfLikesPerPause'])
    PauseInSeconds = int(config['PauseInSeconds'])
    TimeoutPauseInSeconds = int(config['TimeoutPauseInSeconds'])
    MatchesToMessageAmount = int(config['MatchesToMessageAmount'])
    LikePauseInSeconds = float(config['LikePauseInSeconds'])
    UseRandomProxies = int(config['UseRandomProxies'])
    Proxy_List = config['Proxy_List']
    OneAccountPerAnIp = config['OneAccountPerAnIp']
    NeverDeleteProxies = config['NeverDeleteProxies']
    # endregion

    pool = ThreadPool(Threads)
    start_time = time.time()
    auth([(51.5072,-0.1275)])