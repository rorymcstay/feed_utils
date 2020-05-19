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
        cls.__client.images.pull(repository='selenium/standalone-chrome', tag="3.141.59")
        # TODO should handle creation here
        cls.__container = cls.__client.containers.run(os.getenv('BROWSER_IMAGE','selenium/standalone-chrome:3.141.59'),
                ports={'4444/tcp': 4444}, detach=True, remove=True)
        time.sleep(4)

    @classmethod
    def tearDownClass(cls):
        cls.__container.kill()

class KafkaTestInterface(TestCase):


    @classmethod
    def setUpClass(cls):
        kafka_env = [
            "KAFKA_ZOOKEEPER_CONNECT=test_zookeeper:2181",
            "KAFKA_CREATE_TOPICS=\"sample-queue;worker-queue;worker-route;summarizer-route;leader-route\"",
            "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1",
            "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT",
            "KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://test_kafka:9092,PLAINTEXT_HOST://localhost:29092",
            "ALLOW_PLAINTEXT_LISTENER=yes"
        ]
        zookeeper_env = [
            "ZOOKEEPER_CLIENT_PORT=2181",
            "ALLOW_ANONYMOUS_LOGIN=yes",
            "ZOOKEEPER_TICK_TIME=2000"
        ]
        cls.__client = docker.from_env()
        cls.__client.images.pull(repository='confluentinc/cp-kafka', tag="latest")
        cls.__client.images.pull(repository='confluentinc/cp-zookeeper', tag="latest")
        cls.__zookeeper = cls.__client.containers.run(image='confluentinc/cp-zookeeper',name='test_kafka', ports={'9092/tcp': 9092,'29092/tcp':29092},
                environment=zookeeper_env, detach=True, remove=True)
        cls.__kafka = cls.__client.containers.run( image='confluentinc/cp-kafka', name='test_zookeeper', ports={'2181/tcp': 2181},
                environment=kafka_env, detach=True, remove=True)
        # TODO should handle creation here
        time.sleep(10)

    @classmethod
    def tearDownClass(cls):
        cls.__kafka.kill()
        cls.__zookeeper.kill()

class MongoTestInterface(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.__client = docker.from_env()
        cls.__client.images.pull(repository='mongo', tag="latest")
        # TODO should handle creation here
        cls.__container = cls.__client.containers.run(name='test_mongo', image=os.getenv('MONGO_IMAGE','mongo'), ports={'27017/tcp': 27017}, detach=True, remove=True,
                environment=[f'MONGO_INITDB_ROOT_USERNAME={os.environ["MONGO_USER"]}', f'MONGO_INITDB_ROOT_PASSWORD={os.environ["MONGO_PASS"]}'])
        time.sleep(4)
        cls.mongo_client = MongoClient(**mongo_params)

    @classmethod
    def tearDownClass(cls):
        cls.__container.kill()

class PostgresTestInterface(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.__client = docker.from_env()
        cls.__client.images.pull(repository='postgres', tag="latest")
        # TODO should handle creation here
        cls.__container = cls.__client.containers.run(name='test_database', image='postgres', ports={'5432/tcp': 5432}, detach=True, remove=True,
                environment=[f'POSTGRES_PASSWORD={os.environ["DATABASE_USER"]}', f'POSTGRES_USER={os.environ["DATABASE_PASS"]}'])
        time.sleep(4)
        # TODO must make this return a test client aswell

    @classmethod
    def tearDownClass(cls):
        cls.__container.kill()

def ServiceFactory(component):

    class TestInterface(TestCase):
        @classmethod
        def setUpClass(cls):
            test_ports = {
                "ui-server": 5004,
                "nanny": 5003,
                "routing": 5002
            }
            environment = [
                "DATABASE_HOST=test_database",
                "DATABASE_PORT=5432",
                f'DATABASE_USER={os.getenv("DATABASE_USER")}',
                f'MONGO_HOST=test_mongo:27017',
                f'KAFKA_ADDRESS=test_kafka:9092',
                f'MONGO_PASS={os.getenv("MONGO_PASS")}'
                f'MONGO_USER={os.getenv("MONGO_USER")}'
                'ROUTER_HOST=test_router',
                'NANNY_HOST=test_nanny',
                'FLASK_PORT=5000'
            ]

            versions = {}
            with open(f'{os.getenv("DEPLOYMENT_ROOT")}/etc/manifest.txt', 'r') as manifest:
                for item in filter(lambda line: line.strip() != '',  manifest.read().split('\n')):
                    versions.update({item.split("=")[0]: item.split('=')[1]})
            serviceVersion = versions.get(component)
            cls.__client = docker.from_env()
            cls.__client.images.pull(repository=f'{os.getenv("IMAGE_REPOSITORY")}/feed/{component}', tag=serviceVersion)
            # TODO should handle creation here
            cls.__container = cls.__client.containers.run(f'{os.getenv("IMAGE_REPOSITORY")}/feed/{component}:{serviceVersion}', name=f'test_{component}', ports={f'{test_ports.get(component)}/tcp': 5000}, detach=True, remove=True,
                    environment=environment)
            time.sleep(5)
            # TODO must make this return a test client aswell

        @classmethod
        def tearDownClass(cls):
            time.sleep(60)
            cls.__container.kill()

    return TestInterface


