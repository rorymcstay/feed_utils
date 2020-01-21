import inspect
import json
import logging
import re
from inspect import getfullargspec
from json import JSONDecodeError
from typing import List, Dict
from flask import Flask, Response, request, Request

NOT_IMPLEMENTED = 509
WRONG_NUMBER_ARGS = 510
FAIL_CODE = 511
IGNORE_FAILS = True
TEST_CLAUSES = ["request", "response", "payload"]
MANDATORY = ["request", "response"]
JSON_CHARS = '}{:,"'
METHOD_POS = 2  # if leading slash, method name will be in second chunk of request


class MethodNotImplemented(Response):
    def __init__(self):
        super().__init__('MethodNotImplemented', status=404)


class URLArgumentError(Response):
    def __init__(self, expected, actual):
        super().__init__(f'wrong number of args, expected: {expected}, actual: {actual}', status=404)


class FailResponse(Response):
    def __init__(self, reason):
        super().__init__(reason, status=FAIL_CODE)


class ExpectedRequest:
    methods: List[str]
    cases: Dict[str, dict] = {}

    def __init__(self, methods: List[str] = None, cases=None, isMock=True):
        self.cases = cases
        self.methods = methods
        self.isMock = isMock
        self.actualResponse = None
        self.actualPayload = None
        self.actualCase = None

        '''func = getattr(self, f'_{clause}')
        if func is None:
            assert (f'method _{clause} is not implemted' and False)'''

        for i in self.cases:
            case = self.cases.get(i)
            for clause in case:
                logging.info(f'_{clause} for method cases: {self.cases.keys()} has been implemented')
                if case is not None and all(ch in case.get(clause) for ch in JSON_CHARS):
                    try:
                        json.loads(case.get(clause))
                    except JSONDecodeError as e:
                        assert (False and f'{clause} of {i.split("/")[1]} for test case {i} is not valid. JSONDecodeError \
                                postion: {e.pos} line: {e.lineno} col: {e.colno} message: {e.msg}' or IGNORE_FAILS)

    @staticmethod
    def getmethodfrompath(uri):
        method = uri.split('/')[METHOD_POS]
        return method

    def handleRequest(self, requestContext: Request):
        self.actualPayload = requestContext.json if 'json' in requestContext.mimetype else None
        self.actualResponse = None
        self.actualCase = self.getmethodfrompath(requestContext.path)
        self.actualMethod = requestContext.method

        assert (requestContext.method in self.methods and f'{self.actualCase} had invalid method usage, \
               actual was: {requestContext.method}, expected: {self.methods}' or IGNORE_FAILS)
        self._request()
        self._payload()
        return self._response()

    def handleTest(self, case):
        self._response(case, {})

    def _request(self):
        action = self.cases.get(self.actualCase)
        if action is None:
            return FailResponse(
                f'specific scenario not found actual: {self.actualCase}, expected one of: {self.cases.keys()}')

    def _response(self, actual=None):
        caseDetails = self.cases.get(self.actualCase)
        if caseDetails is None:
            logging.error(False and f'{self.actualCase} is not implemented')
            return FailResponse('case not found')

        if self.actualMethod not in self.methods:
            return FailResponse('wrong method')
        type = 'text' if all(c not in self.actualResponse for c in JSON_CHARS) else 'json'
        res = Response(self.actualResponse, status=200, mimetype=type)
        if self.isMock:
            assert (type == res.mimetype and f'wrong mimetype returned \
                    \n  expected: {type}\nactual: {res.mimetype}' or IGNORE_FAILS)
            assert (res.json == self.actualResponse.json() and f'repsonse was invalid. \
                    \n  expected: {json.dumps(res.json(), indent=4)}\nactual: {json.dumps(self.actualResponse.json(), indent=4)}'
                    or IGNORE_FAILS)
            return
        return res

    def _payload(self):
        payload = self.cases.get(self.actualCase).get('payload')
        logging.info(f'received payload to endpoint {self.actualCase}: {json.dumps(self.actualPayload)}')
        assert (self.actualPayload.keys() == payload.keys() and f'body of request {self.actualCase} was malformed. \
                \nactual: {json.dumps(request.json())}\nexpected: {json.dumps(payload)}' or IGNORE_FAILS)


class DocumentationTest:
    _itemsregex = re.compile(f'(#{":|#".join(TEST_CLAUSES)}:)')
    _nameRegex = re.compile('<.*/>')
    _methodsRegex = re.compile('methods=\[')

    def __init__(self, func: callable):
        self.name = func
        self.source = str(func.__doc__)

    @staticmethod
    def _testCaseRegex(name):
        return re.compile(f'(<{name}>|<{name}/>)')

    def getValidMethods(self):
        dec = inspect.getsource(self.name).split("\n")[0]
        out = []
        default = ['GET']
        substrs = dec.split('methods')
        if len(substrs) == 1 or '@route' not in dec:
            return default
        substrs = substrs[1].split(']')
        i, loc = 0, None
        while i < len(substrs):
            if any(met in substrs[i] for met in ['GET', 'POST', 'DELETE', 'PUT']):
                loc = i
                break
            i += 1
        if loc is None:
            return default
        methods = substrs[loc].split(']')[0].replace('=', '').replace('[', '')
        methodList = methods.replace('"' if '"' in methods else "'", '').split(',')
        methodList = [met.strip() for met in methodList]
        return methodList

    def getTestClauses(self, name):
        res = DocumentationTest._testCaseRegex(name).split(self.source.replace("\n", " "))
        case = list(filter(lambda item: all(clause in item for clause in MANDATORY)
                                        and not all(ch in item for ch in '</>'), res))
        logging.info(f'found test case name: {name}')
        out, i = {}, 0
        clauses = case[0].split()
        while i < len(clauses):
            if any(clause in clauses[i] for clause in TEST_CLAUSES):
                clause = clauses[i]
                det = ''
                i += 1 if len(clauses) > i else 0
                while not any(clau in clauses[i] for clau in TEST_CLAUSES) and i < len(clauses):
                    det += clauses[i]
                    i += 1
                    if i >= len(clauses):
                        break
                out.update({clause.replace('#', '').replace(':', ''): det.strip()})
                if i >= len(clauses):
                    break
            else:
                i += 1
                continue
        return out

    def getNames(self):
        res: List[str] = self._nameRegex.findall(str(self.source))
        return [r.strip("/<>") for r in res]

    @staticmethod
    def generate(func: callable) -> ExpectedRequest:
        # TODO when func has no arguments, we only can store one case as we store in map with the url.
        # TODO should have some sort of multimap or list of dicts
        doc = DocumentationTest(func)
        names = doc.getNames()
        caseResponses = {}
        for name in names:
            items = doc.getTestClauses(name)
            if len(items) != 0 and name is not None:
                for i in MANDATORY:
                    if items.get(i) is None:
                        assert (False and f'missing mandatory item {i} in testcase {name} for {func}')
                case = {}
                for i in TEST_CLAUSES:
                    if i == 'request':
                        req = items.get(i)
                        continue
                    if items.get(i) is None:
                        continue
                    else:
                        case.update({i: items.get(i)})
                uri = req
                caseResponses.update({uri: case})
        methods = doc.getValidMethods()
        return ExpectedRequest(cases=caseResponses, methods=methods)


class MockedMethod:
    expectedRequest: ExpectedRequest

    def __init__(self, method):
        self.argspec = getfullargspec(method)
        self.method = method

    # TODO this method fails when running as expectedRequest is not defined. should fix
    # def __str__(self):
    #   return f'{self.__class__.__name__}: {self.expectedRequest.methods}, \
    #           cases: {json.dumps(self.expectedRequest.cases, indent=4)}'

    def runMethod(self, req: Request):
        self.expectedRequest = DocumentationTest.generate(self.method)
        return self.expectedRequest.handleRequest(req)


def MockFactory(service, app):
    class MockService(service):

        actions: Dict[str, MockedMethod]

        def __init__(self, app):
            self.app = app
            self.cases = {}
            self.actions = {}

        def init(self):
            # TODO non callables not being filtered out... feedName is getting in there
            serviceMethods = [method for method in
                              filter(lambda method: callable(getattr(service, method)) and '_' not in method,
                                     dir(service))]
            for method in serviceMethods:
                args = getfullargspec(getattr(service, method))
                params = "/".join([f'<{pname}>' for pname in args[0][1:]])
                self._mockMethod(method)
                self.app.add_url_rule(f'/{service.get_route_base()}/{method}/{params}', method, self._runMethod)

        def _mockMethod(self, methodName: str):
            method = MockedMethod(getattr(service, methodName))
            self.actions.update({methodName: method})
            logging.debug(f'mocked method on uri: {methodName} with {method}')

        def _runMethod(self, *args):
            uri = request.path
            action = self.actions.get(ExpectedRequest.getmethodfrompath(uri))
            logging.debug(f'running mocked method on uri: {uri} with {action}')
            if action is None:
                return FailResponse('no action')
            compare = len(action.argspec.args) - 1 if 'self' in action.argspec.args else len(action.argspec.args)
            if compare != len(args):
                return URLArgumentError(actual=args, expected=action.argspec)
            return action.runMethod(request)

    return MockService(app)