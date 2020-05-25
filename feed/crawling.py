from feed.logger import getLogger
from queue import Queue
import os
import sys
import traceback
from http.client import RemoteDisconnected
from time import sleep, time
import re
import requests as r
import selenium.webdriver as webdriver
from bs4 import BeautifulSoup
from bs4 import Tag, NavigableString
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import WebDriverException
from urllib3.exceptions import MaxRetryError, ProtocolError
import requests
import threading
import subprocess
import argparse

from feed.settings import nanny_params, browser_params, routing_params
from feed.service import Client

from feed.actionchains import ObjectSearchParams, ActionChain, ClickAction, InputAction, CaptureAction, PublishAction, Action
from feed.actiontypes import ActionableItemNotFound


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
        super().__init__(*args, **kwargs)
        requests.get('http://{host}:{port}/routingcontroller/initialiseRoutingSession/{name}'.format(name=self.name, **routing_params))
        self.kwargs = kwargs
        self.driver = driver

    @staticmethod
    def _get_button_to_click(item, action):
        if not isinstance(item, Tag):
            return item
        if item.text and item.text.upper() == action.text.upper():
            return item
        logging.debug(f'checking Tag with text=[{item.text}]')
        for ch in item.children:
            logging.debug(f'##### {type(ch).__name__} #######')
            if isinstance(ch, NavigableString):
                ch = BrowserActions._searchNavigableStringForTag(ch, action.text)
                logging.debug(f'have navigable string')
                if ch is None:
                    continue
            if isinstance(ch, Tag):
                logging.debug(f'checking child {ch.text}')
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
        logging.info(f'{type(self).__name__}::onClickAction: css=[{action.css}], xpath=[{action.xpath}], text=[{action.text}]')
        try:
            button: WebElement = action.getActionableItem(action, self.driver)
            html_class = button.get_attribute('class')
        except Exception:
            raise ActionableItemNotFound(position=action.position, actionHash=action.getActionHash(), chainName=self.name)
        # TODO an action chain should cash there last interaction in the case of a repeat so it does not havbe to do the searching again.
        if not self._verify_class_string(html_class):
            logging.info(f'{type(self).__name__}::onClickAction: Checking {html_class} for {action.css}')
            html_class = list(filter(lambda item: item in action.css, html_class.split(' ')))[0]
        soup = BeautifulSoup(self.driver.page_source)
        logging.info(f'will search html with html_class=[{html_class}]')
        items = soup.find_all(attrs={'class': html_class})
        if len(items) < 1:
            logging.info(f'{type(self).__name__}::onClickAction: Couldnt find button with class=[{html_class}]')
            pass
        else:
            logging.info(f'{type(self).__name__}::onClickAction: items found from html parse. count={len(items)}')
            for item in items:
                altButton = self._get_button_to_click(item, action)
                if altButton and isinstance(altButton, Tag):
                    classNames = altButton.attrs.get('class')
                    logging.debug(f'checking class names, classNames=[{classNames}], len=[{len(classNames)}]')
                    for className in classNames:
                        elems = self.driver.find_elements_by_class_name(className)
                        logging.info(f'found {len(elems)} with className=[{className}]')
                        if len(elems) == 1:
                            logging.info(f'{type(self).__name__}: found unique button to click with className=[{className}], should only have appeared here once')
                            button = elems[0]
        logging.info(f'{type(self).__name__}::onClickAction(): clicking on text={button.text}')
        clickingFrom = self.driver.current_url
        clickTime = time()
        buttonTxt = button.text
        button.click()
        while ( self.driver.current_url == clickingFrom ) and (time() - clickTime <= 5):
            sleep(0.5)
            if self.driver.current_url == clickingFrom:
                logging.debug(f'{type(self).__name__}::onClickAction(): current url has not changed from clicking on "{buttonTxt}"')
            else:
                logging.debug(f'{type(self).__name__}::onClickAction(): current url has changed from "{clickingFrom}" to "{self.driver.current_url}"')
            logging.info(f'{type(self).__name__}::onClickAction(): current url has changed from "{clickingFrom}" to "{self.driver.current_url}"')
        return [BrowserActions.Return(current_url=self.driver.current_url, name=self.name, action=action, data=None)]

    def onCaptureAction(self, action: CaptureAction):
        data = action.getActionableItem(action, self.driver)
        if data is None:
            raise ActionableItemNotFound(position=action.position, actionHash=action.getActionHash(), chainName=self.name)
        self.rePublish(key=self.driver.current_url, action=action, data=data)
        if not action.isSingle:
            return [BrowserActions.Return(current_url=self.driver.current_url, name=self.name, action=action,data=item) for item in data]
        else:
            return [BrowserActions.Return(current_url=self.driver.current_url, name=self.name, action=action,data=data)]

    def onPublishAction(self, action: PublishAction):
        logging.info(f'{type(self).__name__}::onPublishAction: css=[{action.css}], xpath=[{action.xpath}], text=[{action.text}]')
        try:
            data = action.getActionableItem(action, self.driver)
        except Exception:
            raise ActionableItemNotFound(position=action.position, actionHash=action.getActionHash(), chainName=self.name)
        logging.info(f'{type(self).__name__}::onPublishAction: have found data=[{len(data)}]')
        cls = data[0].get_attribute('class')
        soup = BeautifulSoup(self.driver.page_source)
        items = soup.findAll(attrs={'class': cls})
        out=[]
        for item in items:
            # try find a link on the top most surface of html
            link = item.attrs.get('href')
            if link and action.urlStub in link:
                # if it is in this add and continue
                out.append(link)
                continue
            logging.info(f'{type(self).__name__}::onPublishAction: Link was not immediately available, will try parent')
            # if failure, then try find a parent with regex
            parent = item.findParent(attrs={'href': re.compile(f'{action.urlStub}/*')})
            if parent is None:
                # if nothing found, then try find in children with regex
                child = item.findChild(attrs={'href': re.compile(f'{action.urlStub}/*')})
                logging.info(f'{type(self).__name__}::onPublishAction: Link was not immediately available, will try child')
            else:
                # if parent was found then add the link of it and continue
                logging.info(f'{type(self).__name__}::onPublishAction: Found parent link in parent tag.')
                out.append(parent.attrs.get('href'))
                continue
            if child is None: # were here because regex on parent was unsuccesful as well as the child
                # if link wasn't found in the child then try find 'a' tag of parent
                logging.info(f'{type(self).__name__}::onPublishAction: Link was not found with child, searching parent for a tag')
                parentAtag = item.findParent('a', attrs={'href': re.compile(f'{action.urlStub}/*')})
                link = ''
                if parentAtag:
                    # if found then take the link
                    logging.info(f'{type(self).__name__}::onPublishAction: Found parent "a" tag.')
                    link = parentAtag.attrs.get('href')
                if not parentAtag or action.urlStub not in link:
                    # if no suitable parent found with a tag or it was wrong, then try the same with the child
                    bckup = item.findChild('a', attrs={'href': re.compile(f'{action.urlStub}/*')})
                    logginginfo(f'{type(self).__name__}::onPublishAction: Checking backups for link.')
                    if bckup is not None:
                        link = bckup.attrs.get('href') if action.urlStub in bckup.attrs.get('href') else None
                # if all un succesful then dont add anything
                if link == '':
                    logging.warning(f'{type(self).__name__}::onPublishAction: could not find link to page item for chain=[{self.name}], action=[{action}]')
                    continue
                logging.info(f'{type(self).__name__}::onPublishAction: Found link=[{link}]. ')
                out.append(link)
            else:
                out.append(child.attrs.get('href'))
        if len(out) == 0:
            raise ActionableItemNotFound(position=action.position, actionHash=action.getActionHash(), chainName=self.name)
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
        logging.warning(f'{type(self).__name__}::onInputAction: chain=[{self.name}], action=[{action}]')
        return [BrowserActions.Return(current_url=self.driver.current_url, name=self.name, action=action, data=inputField)]

    def saveHistory(self):
        try:
            logging.info(f'BrowserActions::saveHistory: Saving current_url=[{self.driver.current_url}]')
            requests.get('http://{host}:{port}/routingcontroller/updateHistory/{name}'.format(name=self.name, **routing_params), data=self.driver.current_url)
        except Exception as e:
            logging.warning(f'BrowserActions::saveHistory: router is unavailable.')

    def initialise(self, caller):
        hist = self.recoverHistory()
        logging.info(f'BrowserActions::initialise: recovered history for {self.name}, url=[{hist}]')
        url = hist.get('url')
        if not verifyUrl(url):
            logging.info(f'BrowserActions::initialise: last page url was none from router, response=[{hist}]')
            url= self.startUrl
        logging.debug(f'going to: {url}')
        try:
            self.driver.get(url)
        except WebDriverException:
            logging.warning(f'Webdriver exception on initialisation, will reinitiate web browser')
            caller.renewDriverSession()
            self.driver = caller.driver
            self.driver.get(url)

        ret = BrowserActions.Return(action=None, data=None, current_url=self.driver.current_url, name=self.name)
        caller.initialiseCallback(ret)


class BrowserService:
    retry_wait = 10
    retry_attempts = 10

    browser_action_cli_args = argparse.ArgumentParser()
    browser_process_command_queue = Queue()

    def __init__(self, attempts=0, *args, **kwargs):
        """
        Request a port of the nanny service and then start a webdriver session
        :param attempts: will recursively try to get a container, do not populate
        """
        if os.getenv('START_BROWSER', False):
            self.browser_monitor_thread = threading.Thread(target=BrowserService.beginBrowserThread, args=(self,))
            self.browser_monitor_thread.daemon = True
            self.browser_monitor_thread.start()
            sleep(10)
            logging.info(f'{type(self).__name__}::__init__(): Succesfully started browser process')
        self.driver_url = ''
        self.port = browser_params['port']
        url = f'http://{browser_params["host"]}:{self.port}/wd/hub'
        logging.info(f'browser host is set, using {url}')
        self.driver_url = url
        logging.info(f'Starting remote webdriver with {self.driver_url}')
        self.startWebdriverSession()
        logging.info(f'success')

    def driverHealthCheck(self):
        """
        request the current url from the driver and handle a no active session exception
        """
        try:
            self.driver.current_url
        # TODO here we should be able to detect if
        # 1. Session has expired, invalid session id or similiar
        # 2. process has stopped , we will get a urllib exception
        # 3. there has been a page crash ' WebDriverException
        except Exception as ex:
            logging.warning(f'{type(self).__name__}::driverHealthCheck(): Remote Webdriver session is unhealthy: error=[{type(ex).__name__}], args=[{ex.args}]')
            return False
        return True

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

    def renewDriverSession(self):
        self.renewWebCrawler()

    ###########################
    # following methods are for 
    # managing the selenium-st-
    # andalone-chrom process.

    def _bind_queue_and_log(queue: Queue, log):
        """
        iterate over next queue item or None and an io stream.
        """
        # zip together the next item on the queue or None and the next log line
        for i in log:
            queueItem = next_item = None if queue.empty() else queue.get(block=False)
            sleep(0.01)
            yield i, queueItem

    def beginBrowserThread(self):
        """
        open a process, forward its logs and watch for commands in a queue.
        """
        logging.info(f'BrowserService::beginBrowserThread(): Starting web browser thread')
        with subprocess.Popen(os.getenv('SELENIUM_PROCESS_SCRIPT',  "/opt/bin/start-selenium-standalone.sh"), stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as process:
            for line, command in BrowserService._bind_queue_and_log(self.browser_process_command_queue, process.stdout):
                logging.info(f'BrowserService:: {line}')
                if command is None:
                    logging.debug(f'nothing in queue')
                    continue
                elif command == 'KILL':
                    logging.debug(f'have queue item')
                    logging.info(f'BrowserService::beginBrowserThread(): Killing process {process.id}')
                    process.kill()
                    logging.debug(f'monitor thread is {"alive" if self.browser_monitor_thread.is_alive() else "complete"}')
        logging.info(f'Browser process {process.pid} has been torn down.')

    def _browser_clean_up(self):
        """
        place a clean up command to the thread monitoring the selenium process
        """
        logging.info(f'{type(self).__name__}::_browser_clean_up: sending kill command to browser monitor thread')
        self.browser_process_command_queue.put(item='KILL')




def reportParameter(parameter_key=None):
    endpoint = "http://{host}:{port}/parametermanager/reportParameter/{}/{}/{}".format(
        os.getenv("NAME"),
        parameter_key,
        "leader",
        **nanny_params
    )
    r.get(endpoint)


