from queue import Queue
import logging
import os
import sys
import traceback
from http.client import RemoteDisconnected
from time import sleep, time
import re
import selenium.webdriver as webdriver
from bs4 import BeautifulSoup
from bs4 import Tag, NavigableString
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import WebDriverException, NoSuchElementException
from urllib3.exceptions import MaxRetryError, ProtocolError
import threading
import subprocess
import argparse

from feed.settings import browser_params
from feed.service import Client

from feed.actionchains import ActionChain
from feed.actiontypes import ActionableItemNotFound, ClickAction, InputAction, CaptureAction, PublishAction, Action


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
            self.userID = kwargs.get('userID')

        def __dict__(self):
            return dict(name=self.name, userID=self.userID, current_url=self.current_url, data=self.data, action=self.action.__dict__())

    driver = None # type: WebDriver

    def __init__(self, driver: WebDriver, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.routerClient.get(f'/routingcontroller/initialiseRoutingSession/{self.name}')
        self.kwargs = kwargs
        self.driver = driver
        self.soup = BeautifulSoup("<div>None</div>")
        self.backupKeyIncrement = 0

    @staticmethod
    def _get_button_to_click(item, action):
        # TODO should we validate something is clickable or interactable? I believe possible in selenium to check.
        if not isinstance(item, Tag): # whats the reason for this check? is it bad if not a tag? or should it be validating its something else.
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

    def _update_soup(self):
        logging.info(f'Updating soup for {self}')
        self.soup = BeautifulSoup(self.driver.page_source)

    @staticmethod
    def _searchNavigableStringForTag(navString: NavigableString, text):
        """
        private helper function to search navigavle string rescurively
        """
        if navString == text:
            return BeautifulSoup(str(navString))
        newString = navString.findNextSibling()
        if newString is not None:
            BrowserActions._searchNavigableStringForTag(newString, text)
        else:
            return None

    def _verify_class_string(self, item):
        """
        verify that string is valid class name
        css identifiers sometimes contain "<class_to_apply 1> <class_to_apply_2> ..."
        a space seperated list of class strings, if this is the case we want to search
        with those classes for interactable items.
        """

        if ' ' in item:
            # its a css class list, we should search those classes.
            return False
        else:
            return True

    def onClickAction(self, action: ClickAction):
        """
        Much of this code is ultimatley using user input to find elements,
        then use those elements to find other elements

        Need a smarter way - this is where ML would be handy identifying next buttons from html source and
        where we want to go. Probaly easiest first step.
        """
        logging.info(f'{type(self).__name__}::onClickAction: css=[{action.css}], xpath=[{action.xpath}], text=[{action.text}]')
        try:
            button: WebElement = action.getActionableItem(action, self.driver)
            html_class = button.get_attribute('class')
        except Exception:
            raise ActionableItemNotFound(position=action.position, actionHash=action.getActionHash(), chainName=self.name)
        # TODO an action chain should cache there last interaction in the case of a repeat so it does not havbe to do the searching again.
        if not self._verify_class_string(html_class):
            logging.info(f'{type(self).__name__}::onClickAction: Checking {html_class} for {action.css}')
            html_class = list(filter(lambda item: item in action.css, html_class.split(' ')))[0]
            # we take the first class only, should probably do all but well probably spend all day need a more intelligent way obviously.
        soup = BeautifulSoup(self.driver.page_source)
        logging.info(f'will search html with html_class=[{html_class}]')
        items = soup.find_all(attrs={'class': html_class}) # find all or one, hoping the button is in there with that class name.
        if len(items) < 1:
            logging.info(f'{type(self).__name__}::onClickAction: Couldnt find button with class=[{html_class}]')
            pass
        else:
            logging.info(f'{type(self).__name__}::onClickAction: items found from html parse. count={len(items)}')
            # we search for a unique item using find_all, which means well have a list regardless.
            for item in items:
                altButton = self._get_button_to_click(item, action)
                if altButton and isinstance(altButton, Tag):
                    classNames = altButton.attrs.get('class')
                    logging.debug(f'checking class names, classNames=[{classNames}], len=[{len(classNames)}]')
                    for className in classNames: # why is this a loop?
                        elems = self.driver.find_elements_by_class_name(className)
                        logging.info(f'found {len(elems)} elements with className=[{className}]')
                        if len(elems) == 1:
                            # this generally happens 9/10.
                            logging.info(f'{type(self).__name__}: found unique button to click with className=[{className}], should only have appeared here once')
                            button = elems[0]
                        else:
                            found = False
                            logging.info(f'Checking elems={list(map(lambda item: item.text, elems))}')
                            for item in elems:
                                try:
                                    it = item.find_element_by_link_text(action.text)
                                except NoSuchElementException:
                                    if action.text.upper() in str(item).upper():
                                        it = item
                                    else:
                                        continue
                                if it:
                                    logging.info(f'Found by text {it}, {action.text}')
                                    button = it
                                    found = True
                                    break

        logging.info(f'{type(self).__name__}::onClickAction(): clicking on text={button.text}')
        clickingFrom = self.driver.current_url
        clickTime = time()
        buttonTxt = button.text
        button.click()
        # probe current url to see if we went anywhere, we dont necessarily have to. might aswell put needed timeout to good use.
        while ( self.driver.current_url == clickingFrom ) and (time() - clickTime <= 5): # TODO this could be user defined?
            sleep(0.5)
            if self.driver.current_url == clickingFrom:
                logging.debug(f'{type(self).__name__}::onClickAction(): current url has not changed from clicking on "{buttonTxt}"')
            else:
                logging.debug(f'{type(self).__name__}::onClickAction(): current url has changed from "{clickingFrom}" to "{self.driver.current_url}"')
            logging.info(f'{type(self).__name__}::onClickAction(): current url has changed from "{clickingFrom}" to "{self.driver.current_url}"')
        self._update_soup()
        return [BrowserActions.Return(current_url=self.driver.current_url, userID=self.userID, name=self.name, action=action, data=None)]

    def onCaptureAction(self, action: CaptureAction):
        action.backupKey = f'{self.driver.current_url}'
        data = action.getActionableItem(action, self.driver)
        if data is None:
            raise ActionableItemNotFound(position=action.position, actionHash=action.getActionHash(), chainName=self.name)
        self.rePublish(key=self.driver.current_url, action=action, data=data)
        if not action.isSingle:
            return [BrowserActions.Return(current_url=self.driver.current_url, userID=self.userID, name=self.name, action=action, data=item) for item in data]
        else:
            logging.debug(f'returning data={data}, action={action}')
            return [BrowserActions.Return(current_url=self.driver.current_url, userID=self.userID, name=self.name, action=action,data=data)]

    def onPublishAction(self, action: PublishAction):
        """
        search for and publish the links of an item or card.
        TODO need to put chain to publish to on action - logic in rePublish
        """
        logging.info(f'{type(self).__name__}::onPublishAction: css=[{action.css}], xpath=[{action.xpath}], text=[{action.text}]')
        try:
            data = action.getActionableItem(action, self.driver)
        except Exception:
            raise ActionableItemNotFound(position=action.position, actionHash=action.getActionHash(), chainName=self.name)
        logging.info(f'{type(self).__name__}::onPublishAction: have found data=[{len(data)}]')
        # TODO next 4 lines are prime example of having getActionableItem inherited on the PublishAction class.
        # Then we could have publish action ensure `items` is always a list.
        # at the moment, user specifying non single publish action breaks things. (simple fix just havent used yet)
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
        # TODO should put rePublishing into a callback.
        self.rePublish(key=self.driver.current_url, action=action, data=out)
        if not action.isSingle:
            return [BrowserActions.Return(current_url=self.driver.current_url, userID=self.userID, name=self.name, action=action,data=url) for url in out]
        else:
            return [BrowserActions.Return(current_url=self.driver.current_url, name=self.name, userID=self.userID, action=action,data=out[0])]

    def onInputAction(self, action: InputAction):
        inputField: WebElement = action.getActionableItem(action, self.driver)
        try:
            inputField.send_keys(action.inputString)
        except AttributeError as ex:
            # TODO should also handle element not interactable here and give invalid element found back to user
            # TODO in the above case, should try surrounding elements - general rule should be to go inwards
            raise ActionableItemNotFound(position=action.position, actionHash=action.getActionHash(), chainName=self.name)
        logging.warning(f'{type(self).__name__}::onInputAction: chain=[{self.name}], action=[{action}]')
        return [BrowserActions.Return(current_url=self.driver.current_url, name=self.name, action=action, userID=self.userID, data=inputField)]

    def saveHistory(self):
        try:
            logging.info(f'BrowserActions::saveHistory: Saving current_url=[{self.driver.current_url}]')
            self.routerClient.get(f'/routingcontroller/updateHistory/{self.name}', payload=self.driver.current_url)
        except Exception as e:
            # this type of exception really should be in `Client` itself... maybe?
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
        self._update_soup()

        ret = BrowserActions.Return(action=None, data=None, userID=self.userID, current_url=self.driver.current_url, name=self.name)
        caller.initialiseCallback(ret, chain=self)


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
            # this is only used in containerised running - which is intended for. Local dev this doesn't run
            # as you will have selenium running.
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
        ran in seperate thread, given were generally waiting on remote webbrowser requests,
        fine to probe the std out and std err of the process we started
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
        sellogger = logging.getLogger('crawling.SeleniumProcessLogger')
        sellogger.info(f'BrowserService::beginBrowserThread(): Starting web browser thread')
        # run the selenium standalone script
        with subprocess.Popen(os.getenv('SELENIUM_PROCESS_SCRIPT',  "/opt/bin/start-selenium-standalone.sh"), stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as process:
            for line, command in BrowserService._bind_queue_and_log(self.browser_process_command_queue, process.stdout):
                sellogger.info(f'BrowserService:: {line}')
                if command is None:
                    sellogger.debug(f'nothing in queue')
                    continue
                elif command == 'KILL':
                    sellogger.debug(f'have queue item')
                    sellogger.info(f'BrowserService::beginBrowserThread(): Killing process {process.id}')
                    process.kill()
                    sellogger.debug(f'monitor thread is {"alive" if self.browser_monitor_thread.is_alive() else "complete"}')
        sellogger.info(f'Browser process {process.pid} has been torn down.')

    def _browser_clean_up(self):
        """
        place a clean up command to the thread monitoring the selenium process to kill selenium gracefully and for sure.
        """
        logging.info(f'{type(self).__name__}::_browser_clean_up: sending kill command to browser monitor thread')
        self.browser_process_command_queue.put(item='KILL')




def reportParameter(parameter_key=None):
    pass


