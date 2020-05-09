import docker
from unittest import TestCase
import time
import os
from pymongo import MongoClient
from feed.settings import mongo_params


browser_port = os.getenv('BROWSER_PORT', '4444')


class SeleniumTestInterface(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.__client = docker.from_env()
        # TODO should handle creation here
        cls.__container = cls.__client.containers.run(os.getenv('BROWSER_IMAGE','selenium/standalone-chrome:3.141.59'), ports={'4444/tcp': 4444}, detach=True, remove=True)
        time.sleep(4)

    @classmethod
    def tearDownClass(cls):
        cls.__container.kill()

mongo_port = os.getenv('BROWSER_PORT', '27017')
class MongoTestInterface(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.__client = docker.from_env()
        # TODO should handle creation here
        cls.__container = cls.__client.containers.run(os.getenv('MONGO_IMAGE','mongo'), ports={'4444/tcp': 4444}, detach=True, remove=True)
        time.sleep(4)
        cls.mongo_client = MongoClient(**mongo_params)

    @classmethod
    def tearDownClass(cls):
        cls.__container.kill()

