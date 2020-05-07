from feed.logger import getLogger
import os
import sys
import traceback
from http.client import RemoteDisconnected
from time import sleep
import re
import requests as r
import selenium.webdriver as webdriver
from bs4 import BeautifulSoup
from bs4 import Tag, NavigableString
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from urllib3.exceptions import MaxRetryError, ProtocolError
import requests
import threading
import subprocess
import signal
import argparse

from feed.settings import nanny_params, browser_params, routing_params
from feed.service import Client

from feed.actionchains import ObjectSearchParams, ActionChain, ClickAction, InputAction, CaptureAction, PublishAction, Action

logging = getLogger(__name__)


def verifyUrl(url):
    if url is None:
        return False
    if ' ' in url:
        return False
    if 'http://' in url or 'https://' in url:
        return True
    if 'www' in url:
        return True


class BrowserActions(ActionChain):


    class Return:
        def __init__(self, action: Action, data, current_url, name, *args, **kwargs):
            self.name = name
            self.current_url = current_url
            self.data = data
            self.action = action

        def __dict__(self):
            return dict(name=self.name, current_url=self.current_url, data=self.data, action=self.action.__dict__())

    driver = None # type: WebDriver

    def __init__(self, driver: WebDriver, *args, **kwargs):
        self.browser_action_cli_args.parse_args()
        super().__init__(*args, **kwargs)
        logging.info(f'BrowserActions::__init__: initialising browser action chain {self.name}')
        requests.get('http://{host}:{port}/routingcontroller/initialiseRoutingSession/{name}'.format(name=self.name, **routing_params))
        self.kwargs = kwargs
        self.driver = driver

    @staticmethod
    def _get_button_to_click(item, action):
        if not isinstance(item, Tag):
            return item
        if item.text and item.text.upper() == action.text.upper():
            return item
        logging.info(f'checking Tag with text=[{item.text}]')
        for ch in item.children:
            logging.debug(f'##### {type(ch).__name__} #######')
            if isinstance(ch, NavigableString):
                ch = BrowserActions._searchNavigableStringForTag(ch, action.text)
                logging.debug(f'have navigable string')
                if ch is None:
                    continue
            if isinstance(ch, Tag):
                logging.info(f'checking child {ch.text}')
            but = BrowserActions._get_button_to_click(ch, action)
            if but is not None:
                return but
        else:
            return None

    @staticmethod
    def _searchNavigableStringForTag(navString: NavigableString, text):
        if navString == text:
            return BeautifulSoup(str(navString))
        newString = navString.findNextSibling()
        if newString is not None:
            BrowserActions._searchNavigableStringForTag(newString, text)
        else:
            return None


    def _verify_class_string(self, item):

        if ' ' in item:
            return False
        else:
            return True

    def onClickAction(self, action: ClickAction):
        logging.info(f'BrowserActions::onClickAction: css=[{action.css}], xpath=[{action.xpath}], text=[{action.text}]')
        button: WebElement = action.getActionableItem(action, self.driver)
        html_class = button.get_attribute('class')
        if not self._verify_class_string(html_class):
            logging.debug(f'check {html_class} for {action.css}')
            html_class = list(filter(lambda item: item in action.css, html_class.split(' ')))[0]
        soup = BeautifulSoup(self.driver.page_source)
        logging.debug(f'will search html with html_class=[{html_class}]')
        items = soup.find_all(attrs={'class': html_class})
        if len(items) < 1:
            logging.debug(f'no items found from html parse')
            pass
        else:
            logging.debug(f'items found from html parse. count={len(items)}')
            for item in items:
                logging.info(f'found {item}')
                altButton = self._get_button_to_click(item, action)
                if altButton and isinstance(altButton, Tag):
                    classNames = altButton.attrs.get('class')
                    logging.info(f'checking class names, classNames=[{classNames}], len=[{len(classNames)}]')
                    for className in classNames:
                        elems = self.driver.find_elements_by_class_name(className)
                        logging.info(f'found {len(elems)} with className=[{className}]')
                        if len(elems) == 1:
                            logging.info(f'found unique button to click with className=[{className}], should only have appeared here once')
                            button = elems[0]
        logging.info(f'clicking on text={button.text}')
        button.click()
        return [BrowserActions.Return(current_url=self.driver.current_url, name=self.name, action=action, data=None)]

    def onCaptureAction(self, action: CaptureAction):
        data = action.getActionableItem(action, self.driver)
        self.rePublish(key=self.driver.current_url, action=action, data=data)
        if not action.isSingle:
            return [BrowserActions.Return(current_url=self.driver.current_url, name=self.name, action=action,data=item) for item in data]
        else:
            return [BrowserActions.Return(current_url=self.driver.current_url, name=self.name, action=action,data=data)]

    def onPublishAction(self, action: PublishAction):
        data = action.getActionableItem(action, self.driver)
        cls = data[0].get_attribute('class')
        soup = BeautifulSoup(self.driver.page_source)
        items = soup.findAll(attrs={'class': cls})
        for item in items:
            link = item.attrs.get('href')
            if link and action.urlStub in link:
                out.append(link)
                continue
            parent = item.findParent(attrs={'href': re.compile(f'{action.urlStub}/*')})
            if parents is None:
                child = item.findChild(attrs={'href': re.compile(f'{action.urlStub}/*')})
            else:
                out.append(parent.attrs.get('href'))
                continue
            if child is None:
                parentAtag = item.findParent('a')
                link = ''
                if parentAtag:
                    bckup = parentAtag.attrs.get('href')
                    link = bckup.attrs.get('href')
                if not parentAtag or action.urlStub not in link:
                    bckup = item.findChild('a')
                    link = bckup.attrs.get('href') if action.urlStub in bckup.attrs.get('href') else None
                out.append(link)
            else:
                out.append(child.attrs.get('href'))
        # TODO should put this into a callback
        # TODO should republish chain here
        self.rePublish(key=self.driver.current_url, action=action, data=out)
        if not action.isSingle:
            return [BrowserActions.Return(current_url=self.driver.current_url, name=self.name, action=action,data=url) for url in out]
        else:
            return [BrowserActions.Return(current_url=self.driver.current_url, name=self.name, action=action,data=out[0])]

    def onInputAction(self, action: InputAction):
        inputField: WebElement = action.getActionableItem(action, self.driver)
        inputField.send_keys(action.inputString)
        return [BrowserActions.Return(current_url=self.driver.current_url, name=self.name, action=action, data=inputField)]

    def saveHistory(self):
        requests.put('http://{host}:{port}/routingcontroller/updateHistory/{name}'.format(name=self.name, **routing_params), data=self.driver.current_url)

    def initialise(self, caller):
        hist = self.recoverHistory()
        logging.info(f'recovered history for {self.name}, url=[{hist}]')
        url = hist.get('url')
        if not verifyUrl(url):
            logging.info(f'Url was none from router')
            url= self.startUrl
        logging.debug(f'going to: {url}')
        self.driver.get(url)
        ret = BrowserActions.Return(action=None, data=None, current_url=self.driver.current_url, name=self.name)
        caller.initialiseCallback(ret)


class BrowserService:
    retry_wait = 10
    retry_attempts = 10

    browser_action_cli_args = argparse.ArgumentParser()
    browser_action_cli_args.add_argument("--start-browser", action='store_true')
    _webserver_process = None

    def __init__(self, attempts=0, *args, **kwargs):
        """
        Request a port of the nanny service and then start a webdriver session
        :param attempts: will recursively try to get a container, do not populate
        """
        args = self.browser_action_cli_args.parse_args()
        if args.start_browser:
            self._webserver_process = BrowserService.beginBrowserThread()
        self.driver_url = ''
        self.port = browser_params['port']
        url = f'http://{browser_params["host"]}:{self.port}/wd/hub'
        logging.info(f'browser host is set, using {url}')
        self.driver_url = url
        logging.info(f'Starting remote webdriver with {self.driver_url}')
        self.startWebdriverSession()
        logging.info(f'success')

    def startWebdriverSession(self):
        options = Options()
        options.add_argument("--headless")
        logging.info(f'starting webdriver session with {self.driver_url}')
        self.driver = webdriver.Remote(command_executor=self.driver_url,
                                       desired_capabilities=DesiredCapabilities.CHROME,
                                       options=options)
        logging.info("started webdriver session")

    def renewWebCrawler(self):
        logging.info(f'renewing webcrawler')
        self.driver.quit()
        self.startWebdriverSession()

    @staticmethod
    def beginBrowserThread():
        # TODO consume this into BrowserService
        killer = BrowserKiller()

        def browserLoggingThread(process):
            for line in process.stderr:
                logging.info(f'browser starting on pid={process.pid}')
        with subprocess.Popen("/opt/bin/start-selenium-standalone.sh", stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as process:
            browser_thread = threading.Thread(target=startBrowser, args=(process,))
        browser_thread.daemon = True
        browser_thread.start()
        sleep(10)
        return process

    def _browser_clean_up(self):
        if self._webserver_process:
            self._webserver_process.kill()




def reportParameter(parameter_key=None):
    endpoint = "http://{host}:{port}/parametermanager/reportParameter/{}/{}/{}".format(
        os.getenv("NAME"),
        parameter_key,
        "leader",
        **nanny_params
    )
    r.get(endpoint)


