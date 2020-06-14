import sys
import traceback
import time
import json
from json.decoder import JSONDecodeError
import requests as r
import logging
from flask_classy import FlaskView



class Service(FlaskView):

    def healthCheck(self):
        return "ok"


class Client:
    """
    This class provides a common way to health check other containers and serves
    as a single interface for handling session retrieval and authorisation.
    """
    wait = 10

    def __init__(self, name, attempts=0, check_health=True, behalf=None, chainName=None, **params):
        self.base_route = 'http://{host}:{port}'.format(**params)
        self.behalf = behalf
        self.name = name
        self.chainName = chainName
        if check_health:
            if not self.healthCheck():
                logging.error(f'Health check for {self.name} has failed. Exiting Programme. Bye..')
                sys.exit()

    def healthCheck(self):
        try:
            hc = r.get(f'{self.base_route}/service/healthCheck')
            if 100 < hc.status_code < 300:
                return True
            else:
                logging.warning("health check returned unhealthy status_code=[{hc.status_code}]")
                return False
        except Exception as e:
            traceback.print_exc()
            return False

    def get(self, endpoint, payload=None, resp=False, error=None, **kwargs):
        return self._make_request(r.get, endpoint, payload, resp, error, **kwargs)

    def put(self, endpoint, payload=None, resp=False, error=None, **kwargs):
        return self._make_request(r.put, endpoint, payload, resp, error, **kwargs)

    def post(self, endpoint, payload=None, resp=False, error=None, **kwargs):
        return self._make_request(r.post, endpoint, payload, resp, error, **kwargs)

    def delete(self, endpoint, payload=None, resp=False, error=None, **kwargs):
        return self._make_request(r.delete, endpoint, payload, resp, error, **kwargs)

    def _make_request_args(self, endpoint, payload, **kwargs):
        logging.debug(f'making request on behalf=[{self.behalf}] to {self.name}')
        args = {}
        arg_string = "&".join(list(map(lambda kw: f'{kw}={kwargs.get(kw)}', kwargs)))
        if endpoint[0] == '/':
            endpoint = endpoint [1:]
        if arg_string != '':
            arg_string = f'?{arg_string}'
        url = f'{self.base_route}/{endpoint}{arg_string}'
        headers = {'userID': str(self.behalf)}
        if self.chainName:
            headers.update(chainName=self.chainName)
        if isinstance(payload, dict):
            headers.update({'Content-Type': 'application/json'})
            args.update(json=payload)
        elif payload:
            args.update(data=payload)
        args.update(url=url)
        args.update(headers=headers)
        return args

    def _make_request(self, http_method, endpoint, payload=None, resp=False, error=None, **kwargs):
        req_args = self._make_request_args(endpoint, payload, **kwargs)
        if not resp:
            logging.debug(f'Making call to {self.name} for {req_args.get("url")}')
            http_method(**req_args)
            return
        ret = http_method(**req_args)
        if not (200 <= ret.status_code <= 300):
            logging.warning(f'Invalid response code from {self.name} with {req_args.get("url")}. status_code=[{ret.status_code}]')
            return error
        try:
            data = ret.json()
            logging.debug(f'Got valid response from {self.name} for {req_args.get("url")}, {ret.status_code}')
            if data is None:
                logging.warning(f'Response was None from {self.name} for {req_args.get("url")}')
                return error
            logging.debug(f'Returning data=[{data}]')
            return data
        except JSONDecodeError as ex:
            logging.warning(f'Error decoding data from {self.name} with {req_args.get("url")}. response_headers=[{ret.headers}], status_code=[{ret.status_code}]')
            return error

