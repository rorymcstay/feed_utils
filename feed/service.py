import sys
import time
import json
import requests as r
import logging
from flask_classy import FlaskView



class Service(FlaskView):

    def healthCheck(self):
        return "ok"


class Client:
    max_attempts = 10
    wait = 10

    def __init__(self, name, attempts=0, **params):
        try:
            hc = r.get("http://{host}:{port}/service/healthCheck".format(**params))
            if 100 < hc.status_code < 300:
                self.health = True
                logging.info(f'connected to {name}')
            if hc.status_code is 404:
                logging.warning(f'health check for {name}/{params.get("api_prefix")} was not found')
                raise Exception()
            else:
                logging.info("")
                self.health = False
        except Exception as e:
            attempts += 1
            if attempts < self.max_attempts:
                time.sleep(self.wait)
                logging.warning(f'could not connect to {name}, trying again {self.max_attempts - attempts} more times')
                self.__init__(name, attempts, **params)
            else:
                logging.error(f'could not connect to {name}. Giving up. \nParameters were:  \n{json.dumps(params, indent=4)}')
                sys.exit()

