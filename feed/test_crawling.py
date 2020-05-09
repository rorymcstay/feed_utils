from unittest import TestCase
import logging
import time
import unittest
import os
import docker
from feed.crawling import BrowserService
from feed.testinterfaces import SeleniumTestInterface


class TestBrowserService(SeleniumTestInterface, TestCase):

    def test_driverHealtCheck(self):
        res = self.browserService.driverHealthCheck()
        self.assertTrue(res)
        self.browserService.driver.close()
        res = self.browserService.driverHealthCheck()
        self.assertFalse(res)

    def testRenewWebCrawler(self):
        self.browserService.driver.close()
        self.browserService.renewWebCrawler()
        self.assertTrue(self.browserService.driverHealthCheck())

    def setUp(cls):
        cls.browserService = BrowserService()

    def tearDown(cls):
        cls.browserService.driver.quit()
        del cls.browserService

