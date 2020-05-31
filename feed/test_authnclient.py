import unittest
import requests
from unittest import TestCase
import docker
import time

from authnclient import AuthNClient

 
class TestAuthnClient(TestCase):

    @classmethod
    def setUpClass(cls):
        """
        env_list =[
            "AUTHN_URL=http://localhost:8080",
            "APP_DOMAINS=localhost",
            "DATABASE_URL=sqlite3://:memory:?mode=memory\&cache=shared",
            "SECRET_KEY_BASE=changeme",
            "HTTP_AUTH_USERNAME=hello",
            "HTTP_AUTH_PASSWORD=world"
        ]
        cls.client = docker.from_env()
        cls.cont = cls.client.containers.run('keratin/authn-server:latest', 
                command="./authn migrate && ./authn server",
                ports={'3000/tcp': 8080},
                detach=True, auto_remove=True, environment=env_list)
        time.sleep(2)
        
        Note, to run these tests you must run as the above is not working
        docker run -it --rm   --publish 8080:3000   -e AUTHN_URL=http://localhost:8080   -e APP_DOMAINS=localhost   -e DATABASE_URL=sqlite3://:memory:?mode=memory\&cache=shared   -e SECRET_KEY_BASE=changeme   -e HTTP_AUTH_USERNAME=hello   -e HTTP_AUTH_PASSWORD=world   --name authn_app   keratin/authn-server:latest   sh -c "./authn migrate && ./authn server"

        """

        pass

    @classmethod
    def tearDownClass(cls):
        pass


    @classmethod
    def setUp(cls):
        cls.authn = AuthNClient(authn_url='http://localhost:8080', authn_user='hello', authn_pass='world')
        userSignUp = requests.post(f'{cls.authn.authn_url}/accounts', 
                headers={'Origin': 'http://localhost'},
                json={'username': 'test_user', 'password':'sufficientlyComplexPasswordi!'})

        if userSignUp.status_code != 201:
            userLogin = requests.post(f'{cls.authn.authn_url}/session', 
                    headers={'Origin': 'http://localhost'},
                    json={'username': 'test_user', 'password':'sufficientlyComplexPasswordi!'})
            cls.sessionToken = userLogin.json().get('result').get('id_token')    
        else:
            cls.sessionToken = userSignUp.json().get('result').get('id_token')

    def test_getAccount(self):
        acc = self.authn.getAccount(self.sessionToken)
        self.assertDictEqual({'result': {'deleted': False, 'id': 1, 'locked': False, 'username': 'test_user'}},
                acc)
        

if __name__ == '__main__':
    unittest.main()




