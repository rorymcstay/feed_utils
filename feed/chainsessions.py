import os
from urllib.parse import urlparse
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from pymongo.database import Database
from pymongo.collection import Collection
from datetime import timedelta
from flask.sessions import SessionInterface, SessionMixin
from flask import Flask, session, Request
import time
import logging
import requests


from feed.service import Client
from feed.settings import mongo_params, nanny_params, routing_params, authn_params
try:
    from feed.authnclient import AuthNClient
except ModuleNotFoundError:
    logging.warning('Authorisation capabilities not present')



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

    def open_session(self, app, request: Request, reqUserID=None):
        chainNames = request.path.split("/")
        userID = request.headers.get('userID') if reqUserID is None else reqUserID
        chainName = request.headers.get('chainName', {"$in": chainNames}) # if there is no request header chainName, then we should use the list of url
        currentChain = self._chaindefinitions.find_one({'name': chainName, 'userID': userID}, projection=["name", 'userID'])
        logging.debug(f'Getting session for {currentChain}, userID=[{userID}]')
        if currentChain is None and self.sessionConstructor.__name__ != 'User':
            logging.debug(f'No active session with {chainName}')
            chainSession = self.sessionConstructor(name=None, userID=userID)
        else:
            if currentChain is None:
                currentChain = {}
            logging.info(f'starting session for name=[{chainName}], userID=[{userID}]')
            currentChain.pop('_id', None)
            chainSession = self._open_session(currentChain.get("name"), userID)
            logging.info(f'Opening session for userID=[{currentChain.get("userID")}], chainName=[{currentChain.get("name")}]')
        logging.debug(f'Opened session type {self.sessionConstructor.__name__}')

        # pass a client to the database, and 'clients' containing user info in session.
        chainSession.update({'chain_db': self._client[os.getenv('CHAIN_DB', 'actionChains')],
                             'nanny': Client('nanny', **nanny_params, attempts=1, check_health=False, behalf=userID, chainName=chainSession.name),
                             'router': Client('router', **routing_params, attempts=1, check_health=False, behalf=userID, chainName=chainSession.name),
                             'chainDefinitions': self._chaindefinitions})
        return chainSession

    def save_session(self, app, request, response):
        if session.modified:
            self._save_session(session)

    def __get_session_id(self, chainName):
        if self.sessionConstructor.__name__ == 'User':
            logging.debug('Returning session id for user')
            return {"$regex": ".*"} # no temporal session is linked to a User
        return f'{chainName}-{time.strftime("%d_%m")}'

    def _save_session(self, session):
        sessionOut = session.__dict__()
        if session.__name__ != 'User':
            logging.debug(f'ChainSession is not User')
            sessionOut.update({'session_id': self.__get_session_id(session.name)})
        logging.debug(f'saving session for name=[{self.__get_session_id(session.name)}], userID=[{session.userID}]')
        self._sessioncollection.replace_one({'session_id': self.__get_session_id(session.name), 'userID': session.userID}, replacement=sessionOut, upsert=True)

    def _open_session(self, name, userID):
        sess = self._sessioncollection.find_one({'session_id': self.__get_session_id(name), 'userID': userID})
        if sess is None:
            logging.info(f'Lookup failed for _open_session with name={self.__get_session_id(name)} and userID={userID}.')
            return self.sessionConstructor(name=name, session_id=self.__get_session_id(name), userID=userID)
        else:
            logging.debug(f'Lookup succeeded for _open_session with name={self.__get_session_id(name)}, userID={userID}')
            return self.sessionConstructor(**sess)

#TODO def is_null_session():


class AuthorisedChainSession(ChainSession):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.authn = AuthNClient(**authn_params)

    def open_session(self, app, request: Request):
        id_token = self.authn.getIdToken(request) # we make request on behalf of client to verify who they are.
        logging.debug(f'')
        # TODO need to properly return unauthenticated when the use supplies invalid authentication.
        referer_header = request.headers.get('Referer')
        audience_challenge = urlparse(referer_header).netloc
        logging.debug(f'Attempting to authenticate request with: referer_header=[{referer_header}], audience_challenge=[{audience_challenge}], id_token=[{id_token}]')
        acc = self.authn.getAccount(id_token, audience_challenge)
        logging.debug(f'Authenticated user name=[{acc.get("username")}], userID=[{acc.get("id")}]')
        return super().open_session(app, request, acc.get('id'))


def probeMongo(client):
    try:
        cl = client.server_info()
    except ServerSelectionTimeoutError as ex:
        logging.info(f'trying to connect to mongo with {mongo_params}')
        return False
    return True

def init_app(domainImpl, sessionManager=ChainSession):

    app = Flask(__name__)

    app.permanent_session_lifetime = timedelta(days=31)
    app.secret_key = os.getenv('SECRET_KEY', 'this is supposed to be secret')

    sessionManager = sessionManager(domainImpl)

    app.session_interface = sessionManager

    return app



