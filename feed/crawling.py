import logging as log
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

logging = log.getLogger(__name__)


class CrawlerException(Exception):
    def __init__(self, port):
        if all(char.isdigit() for char in port):
            requests.get("http://{host}:{port}/containercontroller/freeContainer/{sub_port}".format(sub_port=port,
                                                                                                    **nanny_params))
        else:
            sys.exit()


class BrowserService:
    driver: WebDriver
    retry_wait = 10
    retry_attempts = 10

    def __init__(self, attempts=0,
                 getContainerUrl="http://{host}:{port}/{api_prefix}/getContainer".format(**nanny_params)):
        """
        Request a port of the nanny service and then start a webdriver session
        :param attempts: will recursively try to get a container, do not populate
        """

        port = requests.get(getContainerUrl)
        try:
            if not 100 < port.status_code < 400:
                logging.warning(f'nanny returned with {port.status_code}, response was {port.text}')
            else:
                logging.info(f'connecting to container on port {port.text}')
                self.port = port.text
                if not all(char.isdigit() for char in self.port):
                    logging.error(f'Nanny container did not return a valid port number {port.text}')
                    raise CrawlerException(port.text)
                # if no browser params specified then running in docker
                # => different host
                if browser_params['host'] is None:
                    url = f'http://worker-{self.port}:{browser_params["internal_port"]}/wd/hub'
                else:
                    # otherwise always localhost
                    url = f'http://{browser_params["host"]}:{self.port}/wd/hub'

                logging.info(f'Starting remote webdriver with {url}')
                options = Options()
                options.add_argument("--headless")
                self.startWebdriverSession(url, options)
        except Exception as e:
            traceback.print_exc()
            if attempts < self.retry_attempts:
                logging.warning(f'error getting container: {port.text}')
                sleep(self.retry_wait)
                self.__init__(attempts=attempts + 1)
            else:
                logging.error(f'could connect to {getContainerUrl}')
                sys.exit()
        logging.info(f'success')

    def startWebdriverSession(self, url, options):
        self.driver = webdriver.Remote(command_executor=url,
                                       desired_capabilities=DesiredCapabilities.CHROME,
                                       options=options)
        logging.info("started webdriver session")


def reportParameter(parameter_key=None):
    endpoint = "http://{host}:{port}/parametermanager/reportParameter/{}/{}/{}".format(
        os.getenv("NAME"),
        parameter_key,
        "leader",
        **nanny_params
    )
    r.get(endpoint)
