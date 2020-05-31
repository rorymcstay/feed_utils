from jose import jwk
import logging
from jose import jwt
from jose.utils import base64url_decode

import requests
import json


class AuthNClient:

    def __init__(self, authn_url, authn_user, authn_pass):
        self.authn_url = authn_url
        self.auth_creds = (authn_user, authn_pass)
        self.keys = []
        self._load_keys()

    def _load_keys(self):
        jsonkeysRequest = requests.get('http://localhost:8080/jwks')
        jsonkeys = jsonkeysRequest.json().get('keys')
        self.keys = [jwk.construct(key) for key in jsonkeys]

    def verifySession(self, token):
        message, encoded_sig = token.rsplit('.', 1)
        decoded_sig = base64url_decode(encoded_sig.encode('utf-8'))
        res = any(key.verify(message.encode('utf-8'), decoded_sig) for key in self.keys)
        if not res:
            logging.info('Authentication failure, reloading keys to try again.')
            self._load_keys()
            return self.verifySession(token)
        return res

    def _decode_token(self, token, audience):
        message, encoded_sig = token.rsplit('.', 1)
        decoded_sig = base64url_decode(encoded_sig.encode('utf-8'))
        payload = None
        if not self.verifySession(token):
            return payload
        for key in filter(lambda key: key.verify(message.encode('utf-8'), decoded_sig), self.keys):
            jsonrep = key.to_dict()
            logging.debug(f'Succesfully validated key.')
            return jwt.decode(token, jsonrep, audience=audience)

    def getAccount(self, token, audience='localhost'):
        payload = self._decode_token(token,audience) 
        acc = requests.get(f'{self.authn_url}/accounts/{payload.get("sub")}', auth=self.auth_creds)
        return acc.json()
