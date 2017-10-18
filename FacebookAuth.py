import httplib
import random
from threading import Thread
import time
import sqlite3
import shutil
import traceback

from selenium import webdriver
import selenium
from selenium.common.exceptions import ElementNotVisibleException
import ProxyScraper

import client


def selenium_authentication(username, password):
    driver = webdriver.PhantomJS('phantomjs.exe')
#     webdriver.DesiredCapabilities.PHANTOMJS['proxy'] = {
#     "httpProxy":prox.get_proxy(username),
#     "ftpProxy":prox.get_proxy(username),
#     "sslProxy":prox.get_proxy(username),
#     "noProxy":None,
#     "proxyType":"MANUAL",
#     "class":"org.openqa.selenium.Proxy",
#     "autodetect":False
# }
    try:
        driver.get(
            "https://facebook.com/login.php?skip_api_login=1&api_key=464891386855067&redirect_uri=https://www.facebook.com/connect/login_success.html&signed_next=1&next=https%3A%2F%2Fm.facebook.com%2Fv1.0%2Fdialog%2Foauth%3Fredirect_uri%3Dfbconnect%253A%252F%252Fsuccess%26display%3Dtouch%26scope%3Duser_interests%252Cuser_likes%252Cemail%252Cuser_about_me%252Cuser_birthday%252Cuser_education_history%252Cuser_location%252Cuser_activities%252Cuser_relationship_details%252Cuser_photos%252Cuser_status%26type%3Duser_agent%26client_id%3D464891386855067%26ret%3Dlogin&cancel_uri=fbconnect%3A%2F%2Fsuccess%3Ferror%3Daccess_denied%26error_code%3D200%26error_description%3DPermissions%2Berror%26error_reason%3Duser_denied&_rdr")
        driver.find_element_by_id("email").clear()
        driver.find_element_by_id("email").send_keys(username)
        driver.find_element_by_id("pass").clear()
        driver.find_element_by_id("pass").send_keys(password)
        try:
            driver.find_element_by_id("u_0_1").click()
        except ElementNotVisibleException:
            pass

        driver.find_element_by_name("__CONFIRM__").click()
        if driver.capabilities['browserName'] == 'phantomjs':
            past = time.time()
            while 'access_token' not in driver.find_element_by_xpath("//*").get_attribute("outerHTML") or (
                        time.time() - past) > 5000:
                time.sleep(.5)

            url = driver.find_element_by_xpath("//*").get_attribute("outerHTML")
            driver.close()
            print 'Success!', url
            return url
        else:
            past = time.time()
            while 'access_token' not in driver.current_url or (
                        time.time() - past) > 5000:
                time.sleep(.5)
            url = driver.current_url
            driver.close()
            # print 'Success!'
            return url
    except (httplib.BadStatusLine, selenium.common.exceptions.NoSuchElementException,
            selenium.common.exceptions.TimeoutException):
        driver.save_screenshot('screenshot.jpg')
        driver.close()
        raise

    except:
        driver.save_screenshot('screenshot.jpg')
        driver.close()
        print 'Large error'
        print traceback.format_exc()


def get_cursor(database):
    return sqlite3.connect(database).cursor()


def get_token(username, password):
    con = sqlite3.connect('Credentials.db')
    c = con.cursor()
    con2 = sqlite3.connect('FacebookDetails.db')
    c2 = con2.cursor()
    try:
        url = selenium_authentication(username, password)
    except (httplib.BadStatusLine, selenium.common.exceptions.NoSuchElementException) as e:
        print 'Errored...', e
        c.execute('DELETE FROM login_details WHERE username = ?', [username])

        c2.execute('UPDATE login_details SET errored = 1 WHERE username = ? ', [username])
        con.commit()
        con2.commit()
        return
    if url is not None:
        expiration = url.split('=')[4].split('"')[0]
        token = url.split('=')[3].split('&')[0]
        try:
            auth = client.BaseClient(token, username=username).phoneResquest('+123')
            print str(auth)
            authenticated = 'user is already validated' in str(auth)
            banned = auth is None
        except (client.TinderErrorAuthenticating):
            banned = True
        if banned:
            print 'Account is actually banned'
            c.execute('DELETE FROM login_details WHERE username = ?', [username])
            c2.execute('UPDATE login_details SET banned = 1 WHERE username = ? ', [username])
            con2.commit()
            con.commit()
            return
        print authenticated
        c.execute(
            "INSERT OR REPLACE INTO login_details (username,password,token, lastTokenRefresh,authenticated) VALUES (?,?,?,?,?)",
            [username, password, token, time.time() + int(expiration), authenticated])

        c2.execute('UPDATE login_details SET errored = 0, banned = 0 WHERE username = ? ', [username])
        con.commit()
        con2.commit()


def update_accounts():
    con = sqlite3.connect('Credentials.db')
    c = con.cursor()
    users = [[username, token] for username, token in c.execute('SELECT username, token FROM login_details')]
    for username, token in users:
        try:
            authenticated = 'user is already validated' in str(
                client.BaseClient(token, username=username).phoneResquest('+123'))
            c.execute('UPDATE login_details SET authenticated = ? WHERE username = ?', [authenticated, username])
        except client.TinderErrorAuthenticating:
            c.execute('DELETE FROM login_details WHERE username = ?', [username])
        except ValueError:
            pass

    con.commit()


def backup_databases():
    paths = ['Credentials.db', 'FacebookDetails.db', 'data.db']
    for path in paths:
        shutil.copyfile(path, 'backup/' + path)


def get_account():
    con = sqlite3.connect('Credentials.db')
    c = con.cursor()
    username, token = random.choice([x for x in c.execute(
        'SELECT username, token FROM login_details WHERE lasttokenrefresh IS NOT NULL AND lasttokenrefresh > ?  AND (NumberInput = 0 OR NumberInput IS NULL )',
        [time.time()])])
    return [token, get_location(username)]


def set_location(username, lat, lon):
    con = sqlite3.connect('FacebookDetails.db')
    cursor = con.cursor()
    try:
        id = con.execute('SELECT id FROM locations WHERE lat = ? AND lon = ?', [lat, lon]).next()[0]
        cursor.execute('UPDATE login_details SET locationprofileid=? WHERE username = ?', [id, username])
        con.commit()
        return
    except StopIteration:
        pass
    id = cursor.execute('SELECT seq FROM sqlite_sequence').fetchone()[0] + 1
    cursor.execute('INSERT INTO locations (lat, lon, accounts) VALUES (?,?,0)', [lat, lon])
    con.commit()
    cursor.execute('UPDATE login_details SET locationprofileid=? WHERE username = ?', [id, username])
    con.commit()


def get_unauth_account():
    return random.choice([x for x in get_all_unauth_accounts()])


def get_all_unauth_accounts():
    return [[token, get_location(username), username] for username, token in get_cursor('Credentials.db').execute(
        'SELECT username, token FROM login_details WHERE authenticated= 0 AND lasttokenrefresh IS NOT NULL AND lasttokenrefresh > ?  AND (NumberInput = 0 OR NumberInput IS NULL )',
        [time.time()])]


def get_all_accounts():
    return [[token, get_location(username)] for username, token in get_cursor('Credentials.db').execute(
        'SELECT username, token FROM login_details WHERE lasttokenrefresh IS NOT NULL AND lasttokenrefresh > ?  AND (NumberInput = 0 OR NumberInput IS NULL )',
        [time.time()])]


def get_valid_account():
    return random.choice([x for x in get_all_valid_accounts()])


def get_all_valid_accounts():
    return [[username, token, get_location(username), refresh] for username, token, refresh in
            get_cursor('Credentials.db').execute(
                'SELECT username, token, lasttokenrefresh FROM login_details WHERE lasttokenrefresh IS NOT NULL AND authenticated = 1 AND lasttokenrefresh > ?  AND (NumberInput = 0 OR NumberInput IS NULL )',
                [time.time()])]


def authenticate_all():  # Authenticates and stores any new users, and refreshes any expired tokens
    con = sqlite3.connect('Credentials.db')
    con2 = sqlite3.connect('FacebookDetails.db')

    detailsList = [x for x in
                   con2.cursor().execute(
                       'SELECT Username,Password FROM  login_details WHERE banned = 0 AND errored = 0')]  # creats a list of unbanned, unerrored usrs
    preList = [x for x in
               con.cursor().execute('SELECT USERNAME,PASSWORD FROM login_details WHERE lasttokenrefresh> ?',
                                    [
                                        time.time()])]  # Creates a list of accounts that don't need to be refreshed and should be excluded from the refresh list
    real_list = [x for x in detailsList if x not in preList]
    for username, password in real_list[::-1]:
        print 'Getting details from %s , %s' % (username, password)
        get_token(username, password)
    con.close()


def get_location(username=None):
    if username is None:
        con = sqlite3.connect('FacebookDetails.db')
        return con.cursor().execute('SELECT * FROM locations ORDER BY accounts ASC').next()
    else:
        con = sqlite3.connect('FacebookDetails.db')
        return con.cursor().execute(
            'SELECT locations.lat,locations.lon FROM login_details JOIN locations ON login_details.locationprofileid = locations.id WHERE username = ?',
            [username]).next()


def assign_locations():
    con = sqlite3.connect('FacebookDetails.db')
    c = con.cursor()
    users = [x for x in
             c.execute('SELECT username FROM login_details WHERE banned =0 AND errored = 0 AND locationprofileid = 0 ')]
    con.close()
    for username in users:
        temp_con = sqlite3.connect('FacebookDetails.db')
        place, pop, lat, lon, accounts, id = get_location()
        temp_con.cursor().execute('UPDATE login_details SET locationprofileid= ? WHERE username = ?', [id, username[0]])
        temp_con.cursor().execute('UPDATE Locations SET accounts = accounts +1 WHERE id = ? ', [id])
        temp_con.commit()


def load_credentials():  # Loads all usernames and passwords from a text file into the database
    for line in file('FacebookAccounts').readlines():
        place, pop, lat, lon, accounts, id = get_location()
        username, password = line.split(':')[0], line.split(':')[1]
        con = sqlite3.connect('FacebookDetails.db')
        c = con.cursor()
        try:
            c.execute('INSERT INTO login_details VALUES  (?,?,?,?,?)',
                      [username, password, 0, 0, id])
            c.execute('UPDATE Locations SET accounts = accounts +1 WHERE id = ? ', [id])
        except sqlite3.IntegrityError:
            pass
        con.commit()
        con.close()


def refresh_account(username):
    con = sqlite3.connect('Credentials.db')
    c = con.cursor()
    password = c.execute('SELECT password WHERE username = ?', [username]).next()[0]
    get_token(username, password)


class AuthenticationLoop:
    running = True

    def __init__(self):
        Thread(target=self.auth_accounts).start()

    def auth_accounts(self):
        while self.running:
            load_credentials()
            authenticate_all()
            update_accounts()
            time.sleep(10)


if __name__ == '__main__':
    # prox = ProxyScraper.ProxyHandler()
    AuthenticationLoop()