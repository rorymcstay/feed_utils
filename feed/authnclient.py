from jose import jwk
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

    def _load_keys(self):
        """
        Override with specific key grabbing implementation
        """
        raise NotImplementedError()


class UserNotAuthenticated(Exception):
    def __init__(self):
        pass


class AuthNClient(RemoteJWKCache):

    def __init__(self, authn_url, authn_user, authn_pass, *args, **kwargs):
        self.authn_url = authn_url
        self.auth_creds = (authn_user, authn_pass)
        super().__init__(*args, **kwargs)

    def _load_keys(self):
        jsonkeysRequest = requests.get(f'{self.authn_url}/jwks')
        jsonkeys = jsonkeysRequest.json().get('keys')
        logging.debug(f'Loaded {len(jsonkeys)} from authentication server')
        self.keys = [jwk.construct(key) for key in jsonkeys]

    def _decode_token(self, token, audience):
        logging.debug(f'Decoding remote client token, audience=[{audience}]') #TODO figure out exactly why we must specify audience as we are proxying these requests is it valid?
        message, encoded_sig = token.rsplit('.', 1)
        decoded_sig = base64url_decode(encoded_sig.encode('utf-8'))
        logging.debug(f'Decoding token {token}')
        logging.debug(f'Filtering keys of length {self.keys}')
        for key in self.keys:
            jsonrep = key.to_dict()
            logging.debug(f'Have token to decrypt token')
            pl = jwt.decode(token, jsonrep, audience=audience)
            logging.debug(f'payload=[{pl}]')
        logging.warning(f'Could not decode token')
        return payload

    def getAccount(self, token):

        payload = self._decode_token(token, audience=os.getenv('AUTHN_AUDIENCE_CHALLENGE'))# what about checking if this is None
        if not payload:
            logging.error(f'User is not authenticated, payload=[{payload}]')
            raise UserNotAuthenticated()
        logging.debug(f'Succesfully validated key.')
        acc = requests.get(f'{self.authn_url}/accounts/{payload.get("sub")}', auth=self.auth_creds)
        logging.debug(f'Authenticated user: {acc.json()}')
        return acc.json().get('result')

