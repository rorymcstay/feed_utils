from jose import jwk
from flask import Request
import os
import logging
from jose import jwt
from jose.utils import base64url_decode
import threading
from feed.logger import ClassLogger
import time

import requests
import json


class RemoteJWKCache(ClassLogger):

    def __init__(self, refresh_rate=60):
        super().__init__()
        """
        Inherit to get automatic key refesh
        :param: refresh_rate: number of seconds until key expires
        """
        self.keys = []
        self.refresh_rate = refresh_rate
        self._load_keys() # prepopulate cache 
        self._refresh_thread = threading.Thread(target=self._refresh_procedure, args=(), daemon=True)
        self.log.info(f'Starting json web token cache.')
        self._refresh_thread.start()

    def _refresh_procedure(self):
        while True:
            time.sleep(self.refresh_rate)
            self.log.info(f'Refreshing JWKs..., next refresh in {self.refresh_rate} seconds')
            self._load_keys()
            if len(self.keys) == 0:
                self.log.warning(f'Have no keys from web key server, wont be able to authenticate clients')

    def _load_keys(self):
        """
        Override with specific key grabbing implementation
        """
        raise NotImplementedError()


class UserNotAuthenticated(Exception):
    def __init__(self):
        pass


class IdToken:
    time = 0
    def __init__(self, token):
        self.time = time.time()
        self.token = token


class AuthNClient(RemoteJWKCache):

    _instance = None
    _id_token_map = {}
    _timeout = 3600

    def __init__(self, authn_url, authn_user, authn_pass, *args, **kwargs):
        self.authn_url = authn_url
        self.auth_creds = (authn_user, authn_pass)
        super().__init__(*args, **kwargs)

    def _load_keys(self):
        jsonkeysRequest = requests.get(f'{self.authn_url}/jwks')
        jsonkeys = jsonkeysRequest.json().get('keys')
        logging.debug(f'Loaded {jsonkeys} keys from authentication server')
        self.keys = jsonkeys #[jwk.construct(key) for key in jsonkeys]

    def _decode_token(self, token, audience):
        for key in self.keys:
            #jsonrep = key.to_dict()
            logging.debug(f'trying to decrypt token decrypt with audience challeng=[{audience}]')
            pl = jwt.decode(token, self.keys, audience=audience)
            logging.debug(f'payload=[{pl}]')
        logging.warning(f'Could not decode token')
        return pl

    def getAccount(self, token, audience):
        logging.debug(f'Getting details for audience=[{audience}] from token=[{token}]')
        payload = self._decode_token(token, audience)
        if not payload:
            logging.error(f'User is not authenticated, payload=[{payload}]')
            raise UserNotAuthenticated('User is not authenticated')
        logging.debug(f'Succesfully validated key.')
        logging.info(f'requestintg account details for: {payload.get("sub")}')
        acc = requests.get(f'{self.authn_url}/accounts/{payload.get("sub")}', auth=self.auth_creds)
        logging.debug(f'Authenticated user: {acc.json()}')
        return acc.json().get('result')

    def getIdToken(self, request: Request):
        # This needs to be cached somehow
        cookie = request.cookies.get('authn')
        #if self._id_token_map.get(cookie) and (time.time() - self._id_token_map.get(cookie).time < self._timeout):
        #    return self._id_token_map.get(cookie).token
        logging.debug(f'Cookies=[{request.cookies}], Headers=[{request.headers}]')
        cookies = {'authn': request.cookies.get('authn')}
        headers = {'Origin': request.headers.get('Origin'), 'Referer': request.headers.get('Referer')}
        r = requests.get(f'{self.authn_url}/session/refresh', headers=headers, cookies=cookies)
        # there is no cookie on return.
        return r.json().get('result').get('id_token')



