from feed.logger import getLogger
import os
import sys
import traceback
from http.client import RemoteDisconnected
from time import sleep

import requests as r
import selenium.webdriver as webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.remote.webdriver import WebDriver
from urllib3.exceptions import MaxRetryError, ProtocolError
import requests

from feed.settings import nanny_params, browser_params
from feed.service import Client

logging = getLogger(__name__)


class BrowserService:
    driver: WebDriver
    retry_wait = 10
    retry_attempts = 10

    def __init__(self, attempts=0):
        """
        Request a port of the nanny service and then start a webdriver session
        :param attempts: will recursively try to get a container, do not populate
        """
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


def beginBrowserThread():
    def startBrowser():
        with subprocess.Popen("/opt/bin/start-selenium-standalone.sh", stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as process:
            for line in process.stderr:
                logging.info(f'browser starting on pid={browserProcess.pid}')

    browser_thread = threading.Thread(target=startBrowser)
    browser_thread.daemon = True
    browser_thread.start()
    sleep(10)
    return browser_thread

def reportParameter(parameter_key=None):
    endpoint = "http://{host}:{port}/parametermanager/reportParameter/{}/{}/{}".format(
        os.getenv("NAME"),
        parameter_key,
        "leader",
        **nanny_params
    )
    r.get(endpoint)
