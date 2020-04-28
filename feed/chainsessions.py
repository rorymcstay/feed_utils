import os
from pymongo import MongoClient
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

        self._client = MongoClient(**mongo_params)
        self.sessionConstructor = sessionType
        self._sessioncollection = self._client[os.getenv('SESSION_DATABASE', 'sessions')][f'{type(sessionType).__name__}Sessions']
        self._chaindefinitions = self._client[os.getenv('ACTIONCHAIN_DATABASE', 'actionChains')]['actionChainDefinitions']

    def open_session(self, app, request):
        chainNames = request.path.split("/")
        name = self._chaindefinitions.find_one({'name': {"$in": chainNames}}, projection=["name"])
        if name is None:
            return self.sessionConstructor(name=None)
        else:
            logging.info(f'starting session for name=[{name.get("name")}]')
            return self._open_session(name=name.get('name'))

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
            return self.sessionConstructor(name=name)
        else:
            return self.sessionConstructor(**sess)

#TODO    def is_null_session():


