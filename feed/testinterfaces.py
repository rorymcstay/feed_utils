import docker
from unittest import TestCase
import time
import os
from pymongo import MongoClient
from feed.settings import mongo_params


browser_port = os.getenv('BROWSER_PORT', '4444')

base_params=dict(detach=True,
                 remove=True,
                 network='test')


sample_chain = dict(actions=[{"actionType": "CaptureAction", "css": ".card__body", "xpath": "//*[contains(concat( \" \", @class, \" \" ), concat( \" \", \"card__body\", \" \" ))]", "text": ""}], name='test_chain', startUrl='https://example.com', isRepeating=False)


class SeleniumTestInterface(TestCase):

    @classmethod
    def createSelenium(cls):
        cls.__client = docker.from_env()
        cls.__client.images.pull(repository='selenium/standalone-chrome', tag="3.141.59")
        # TODO should handle creation here
        cls.__selenium = cls.__client.containers.run(image='selenium/standalone-chrome:3.141.59', name='test_selenium',
                                                     ports={'4444/tcp': 4444}, **base_params)

    def killSelenium():
        __selenium = docker.from_env().containers.get('test_selenium')
        __selenium.kill()


class KafkaTestInterface(TestCase):

    @classmethod
    def createKafka(cls):
        cls.__client = docker.from_env()
        kafka_env = [
            "KAFKA_ZOOKEEPER_CONNECT=test_zookeeper:2181",
            "KAFKA_CREATE_TOPICS=\"sample-queue;worker-queue;worker-route;summarizer-route;leader-route\"",
            "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1",
            "KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:29092",
            "ALLOW_PLAINTEXT_LISTENER=yes"
        ]
        zookeeper_env = [
            "ZOOKEEPER_CLIENT_PORT=2181",
            "ALLOW_ANONYMOUS_LOGIN=yes",
            "ZOOKEEPER_TICK_TIME=2000"
        ]
        try:

            cls.__zookeeper = cls.__client.containers.run(image='confluentinc/cp-zookeeper',
                                                          name='test_zookeeper',
                                                          ports={'2181/tcp': 2181},
                                                          environment=zookeeper_env,
                                                          **base_params)
        except docker.errors.APIError as ex:
            if ex.status_code != 409:
                raise ex
        try:
            cls.__kafka = cls.__client.containers.run(image='confluentinc/cp-kafka',
                                                      name='test_kafka',
                                                      ports={'29092/tcp':29092},
                                                      environment=kafka_env,
                                                      **base_params)
            print('created kafka and zookeeper container')
        except docker.errors.APIError as ex:
            if ex.status_code != 409:
                raise ex

    def killKafka():
        __kafka = docker.from_env().containers.get('test_kafka')
        __zookeeper = docker.from_env().containers.get('test_zookeeper')
        __kafka.kill()
        __zookeeper.kill()


class MongoTestInterface:

    @classmethod
    def createMongo(cls):
        cls.__client = docker.from_env()
        cls.__client.images.pull(repository='mongo', tag="latest")
        # TODO should handle creation here
        try:
            cls.__mongo = cls.__client.containers.run(name='test_mongo',
                                                      image=os.getenv('MONGO_IMAGE','mongo'),
                                                      ports={'27017/tcp': 27017},
                                                      detach=True,
                                                      remove=True,
                                                      environment=[f'MONGO_INITDB_ROOT_USERNAME={os.environ["MONGO_USER"]}', f'MONGO_INITDB_ROOT_PASSWORD={os.environ["MONGO_PASS"]}'])
            time.sleep(3)
        except docker.errors.APIError as ex:
            if ex.status_code != 409:
                raise ex
        print('created docker image!')

        cls.mongo_client = MongoClient(**mongo_params)
        cls.mongo_client['actionChains']['actionChainDefinitions'].replace_one({'name': sample_chain.get('name')}, replacement=sample_chain, upsert=True)

    def killMongo():
        __container = docker.from_env().containers.get('test_mongo')
        __container.kill()


class PostgresTestInterface(TestCase):

    @classmethod
    def createPostgres(cls):
        cls.__client = docker.from_env()
        cls.__client.images.pull(repository='postgres', tag="latest")
        try:
            cls.__postgres = cls.__client.containers.run(name='test_database',
                                                          image='postgres',
                                                          ports={'5432/tcp': 5432},
                                                          environment=[f'POSTGRES_PASSWORD={os.environ["DATABASE_USER"]}', f'POSTGRES_USER={os.environ["DATABASE_PASS"]}'], **base_params)
        except docker.errors.APIError as ex:
            if ex.status_code != 409:
                raise ex

    def killPostgres():
        __postgres = docker.from_env().containers.get('test_database')
        __postgres.kill()

def ServiceFactory(component):
    """
    Create a service interface from a component name for test dependencies

    """

    def kill():
        __client = docker.from_env()
        try:
            __client.containers.get(f'test_{component}')
        except docker.errors.NotFound as ex:
            print(ex.args)
            pass


    def create():
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
            f'KAFKA_ADDRESS=localhost:29092',
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
        __client = docker.from_env()
        # TODO should handle creation here
        try:
            __container = __client.containers.run(f'{os.getenv("IMAGE_REPOSITORY")}/feed/{component}:{serviceVersion}', name=f'test_{component}', ports={f'{test_ports.get(component)}/tcp': 5000}, detach=True, remove=True,
                    environment=environment)
        except docker.errors.APIError as ex:
            if (ex.status_code != 409) and  (ex.status_code != 500):
                raise ex
    class TestInterface:
        pass

    setattr(TestInterface, f'create{component.capitalize()}', create)
    setattr(TestInterface, f'kill{component.capitalize()}', kill)

    return TestInterface


