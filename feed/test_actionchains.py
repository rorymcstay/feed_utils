from unittest import TestCase
import logging
import time
import unittest
import os
import docker
from feed.crawling import BrowserService, BrowserActions
from feed.actionchains import CaptureAction
from feed.actionchains import CaptureAction, ClickAction, PublishAction, InputAction

#from feed.testutils import MockFactory # in order to mock the routing factory we will need the application code
# other option: build a test image which runs the mock?
# an environment variable and an image which pulls the application code to a certain version and mocks it?

test_action_chain = {}
browser_port = os.getenv('BROWSER_PORT', '4444')

crawling = logging.getLogger('feed.crawling')
actions = logging.getLogger('feed.actionchains')
sh = logging.FileHandler('/home/rory/app/feed/tmp/logs/feed.crawling.logs')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s -%(message)s')
sh.setLevel(logging.DEBUG)
sh.setFormatter(formatter)
crawling.addHandler(sh)
actions.addHandler(sh)


class TestBrowserActions(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.__client = docker.from_env()
        # TODO should handle creation here
        cls.__container = cls.__client.containers.run(os.getenv('BROWSER_IMAGE','selenium/standalone-chrome:3.141.59'), ports={'4444/tcp': 4444}, detach=True, remove=True)
        time.sleep(4)

    @classmethod
    def tearDownClass(cls):
        cls.__container.kill()

    def setUp(cls):
        cls.browserService = BrowserService()
        cls.actionChain = BrowserActions(driver=cls.browserService.driver, **test_action_chain)

    def tearDown(cls):
        cls.browserService.driver.quit()
        del cls.browserService

    def test_onCaptureAction(cls):
        action = CaptureAction(position=0, captureName='donedeal_test', **{"actionType": "CaptureAction", "css": ".card__body", "xpath": "//*[contains(concat( \" \", @class, \" \" ), concat( \" \", \"card__body\", \" \" ))]", "text": "", "inputString": "Example Search input", "undefined": ""})
        cls.actionChain.driver.get("https://www.donedeal.co.uk/cars")
        ret = cls.actionChain.onCaptureAction( action)
        for item in ret:
            print(item.data)
            cls.assertIsNotNone(item)
        cls.failIf(len(ret) is 0)

    def test_onPublishAction(cls):
        action = PublishAction(position=0, **{"actionType": "PublishAction", "css": ".card__body", "xpath": "//*[contains(concat( \" \", @class, \" \" ), concat( \" \", \"card__body\", \" \" ))]", 'text': ''})
        cls.actionChain.driver.get("https://www.donedeal.co.uk/cars")
        ret = cls.actionChain.onPublishAction(action)
        for item in ret:
            cls.failIf('https://' not in ret.data)

    #TODO on input action tests

    def test_onClickAction(cls):
        startUrl = "https://www.donedeal.co.uk/cars"
        cls.actionChain.driver.get(startUrl)
        action = ClickAction(position=0, **{"actionType": "ClickAction", "css": ".ng-isolate-scope", "text": "Next", 'xpath':'//*[contains(concat( " ", @class, " " ), concat( " ", "ng-isolate-scope", " " ))]' })
        cls.actionChain.onClickAction(action)
        time.sleep(3)
        cls.assertNotEqual(cls.actionChain.driver.current_url, startUrl)


if __name__ == '__main__':
    unittest.main()

