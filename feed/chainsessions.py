import os
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from pymongo.database import Database
from pymongo.collection import Collection
from datetime import timedelta
from flask.sessions import SessionInterface, SessionMixin
from flask import Flask, session
import time
import logging
from feed.settings import mongo_params


class ChainSession(SessionInterface):

    _sessioncollection: Collection = None
    _chaindefinitions: Collection = None
    sessionConstructor = None
    _client: MongoClient = None

    def __init__(self, sessionType):
        logging.info(f'Starting ChainSession mananager with sessionType=[{sessionType.__name__}] and parameters=[{mongo_params}]')
        self._client = MongoClient(**mongo_params)
        self.sessionConstructor = sessionType
        self._sessioncollection = self._client[os.getenv('CHAIN_DB', 'actionChains')][f'{sessionType.__name__}Sessions']
        self._chaindefinitions = self._client[os.getenv('CHAIN_DB', 'actionChains')]['actionChainDefinitions']

    def is_null_session(self, sessionObj):
        if sessionObj.name:
            logging.info(f'found null session {sessionObj.name}')
            return False
        else:
            return True

    def open_session(self, app, request):
        chainNames = request.path.split("/")
        name = self._chaindefinitions.find_one({'name': {"$in": chainNames}}, projection=["name"])
        if name is None:
            chainSession = self.sessionConstructor(name=None)
        else:
            logging.info(f'starting session for name=[{name.get("name")}]')
            chainSession = self._open_session(name=name.get('name'))

        chainSession.update({'chain_db': self._client[os.getenv('CHAIN_DB', 'sessions')],
                             'chainDefinitions': self._chaindefinitions})
        return chainSession

    def save_session(self, app, request, response):
        if session.modified:
            self._save_session(session)

    @staticmethod
    def get_session_id(chainName):
        return "{}-{}".format(chainName, time.strftime("%d_%m"))

    def _save_session(self, session):
        sessionOut = session.__dict__()
        sessionOut.update({'session_id': ChainSession.get_session_id(session.name)})
        logging.info(f'saving session for name=[{session.name}]')
        self._sessioncollection.replace_one({'session_id': ChainSession.get_session_id(session.name)}, replacement=sessionOut, upsert=True)

    def _open_session(self, name):
        # TODO: session id logic
        sess = self._sessioncollection.find_one({'session_id': ChainSession.get_session_id(name)})
        if sess is None:
            return self.sessionConstructor(name=name, session_id=ChainSession.get_session_id(name))
        else:
            return self.sessionConstructor(**sess)




#TODO def is_null_session():

def probeMongo(client):
    try:
        cl = client.server_info()
    except ServerSelectionTimeoutError as ex:
        logging.info(f'trying to connect to mongo with {mongo_params}')
        return False
    return True

def init_app(domainImpl):

    app = Flask(__name__)

    app.permanent_session_lifetime = timedelta(days=31)
    app.secret_key = os.getenv('SECRET_KEY', 'this is supposed to be secret')

    sessionManager = ChainSession(domainImpl)

    while not probeMongo(sessionManager._client):
        time.sleep(10)

    app.session_interface = sessionManager

    return app



