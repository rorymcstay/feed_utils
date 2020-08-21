import logging
import os
import hashlib
import traceback
import requests
import json
from json.encoder import JSONEncoder
from bs4 import BeautifulSoup, Tag
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.remote.webdriver import WebDriver
import signal


from kafka import KafkaConsumer, KafkaProducer

from feed.service import Client
from feed.settings import kafka_params, routing_params, nanny_params
from feed.actiontypes import Action, \
        ActionChainException, \
        ClickAction, \
        InputAction, \
        CaptureAction, \
        PublishAction



class GracefulKiller:
    kill_now = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self,signum, frame):
        self.kill_now = True



class ObjectSearchParams:
    """
    Base class for to hold parameters for an item on page, and verifies the items
    found are of the correct quantity.
    """
    def __init__(self, **kwargs):
        #super().__init__(**kwargs)
        self.isSingle = kwargs.get('isSingle', False)
        self.returnType = kwargs.get('returnType', 'src') # see actiontypes.py ReturnType
        self.attribute = kwargs.get('attribute', None)

    def __dict__(self):
        return self.kwargs

    def _verifyResultLength(self, items):
        if len(items) == 0:
            return False
        if self.isSingle and len(items) > 1:
            self.backup = items
            return False
        else:
            return True

    def _returnItem(item, driver):
        raise NotImplementedError
    def search(item, driver):
        raise NotImplementedError


class BrowserSearchParams(ObjectSearchParams):
    """
    TODO: Move this to crawling.py as it is specific to selenium driver.
    Implementation for browser driver ObjectSearchParams.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.kwargs = kwargs
        self.css = kwargs.get('css')
        self.xpath = kwargs.get('xpath')
        self.text = kwargs.get('text')
        #self.text = kwargs.get('class')
        self.backup = None

    def _returnItem(self, item: WebElement, driver: WebDriver): # -> ReturnItem
        """
        given a located element of the page, and the caller's webdriver, return the item depending on the
        return type.

        """
        logging.debug(f'returning returnType=[{self.returnType}] type for actionType=[{type(self).__name__}]')
        # define formatter (callable) depending on the returnType
        if self.returnType == 'text':
            formatted = lambda item: item.text
        elif self.returnType == 'src':
            classes = set([element.get_attribute('class') for element in item])
            soup = BeautifulSoup(driver.page_source)
            out = []
            for cls in classes:
                logging.debug(f'ObjectSearchParam::_returnItem(): searching for node with attribues, class=[{cls}]')
                out.extend(soup.findAll(attrs={'class': cls}))
            item = out
            formatted = lambda it: (it, it.find_parent("a").attrs if it.find_parent('a') is not None else {})
        elif self.returnType == 'attr':
            formatted = lambda element: element.get_attribute(self.attribute)
        elif self.returnType == 'element':
            formatted = lambda it: it
        logging.debug(f'ObjectSearchParams::_returnItem(): returning {len(item)}.')
        retVal = list(map(formatted, item))
        if len(retVal) == 0:
            logging.warning(f'No items found for item return for {type(self).__name__}.')
            return None
        if len(retVal) == 1:
            return retVal[0]
        else:
            return retVal

    def search(self, driver) -> WebElement:

        # first try css selector
        logging.info(f'{type(self).__name__}::search(driver): searching for elemnent with css=[{self.css}]')
        ret = driver.find_elements_by_css_selector(self.css)
        if self._verifyResultLength(ret):
            logging.info(f'BrowserSearchParams::search(): found elements count=[{len(ret)}], isSingle=[{self.isSingle}] with css')
            return self._returnItem(ret, driver)

        # then try xpath
        logging.info(f'{type(self).__name__}::search(driver): searching for elemnent with xpath=[{self.xpath}]')
        ret = driver.find_elements_by_xpath(self.xpath)
        if self._verifyResultLength(ret):
            logging.info(f'BrowserSearchParams::search: found element [{ret}] with xpath')
            return self._returnItem(ret, driver)

        # TODO: should search backup list with text at this point
        if self.backup:
            for res in filter(lambda item: item.text.upper() == self.text, self.backup):
                logging.debug(f'using element [{ret}] from backup')
                return self._returnItem([ret], driver)
            return self._returnItem([self.backup[0]], driver)
        else:
            # TODO brute search with text at this point
            return None

class ActionChain:
    """
    a list of Actions and methods to support the running of a series of Actions.

    an action has a type, and the action chain has a specific handler method for each
    particular action.
    :param: name : name of actionchain
    :param: startUrl: the starting homepage of the procedure
    :param: repeating: should the actionchain run repeatedly
    :param: userID: the user id who requested the actionchain to be ran.
    :param: actions: A list of Action parameters key value pairs.
    """
    actions= {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.name = kwargs.get('name')
        self.startUrl = kwargs.get('startUrl')
        self.repeating = kwargs.get('isRepeating', True)
        self.userID = kwargs.get('userID', None)
        actionParams = kwargs.get('actions', [])
        self.isSample = False

        # ActionChain has it's own implementation of a http client (a wrapper around requests lib) 
        # so that we can have implementation of sessions/cookies and or auth amongst services
        # in the same place, amongst other things.
        # TODO should enable and disable nanny/router usage by environment variable to aid unit testing.
        self.nannyClient = Client('nanny', behalf=self.userID, check_health=False, **nanny_params)
        self.routerClient = Client('router', behalf=self.userID, check_health=False, **routing_params)
        self.failedChain = False
        for order, params in enumerate(actionParams):
            try:
                action = ActionChain.actionFactory(position=order, actionParams=params)
                self.actions.update({order: action})
            except KeyError as ex:
                # TODO: wAt this point we should pass this onto the user
                traceback.print_exc()
                logging.error(f'{type(self).__name__}::__init__(): chainName=[{self.name}], position=[{order}] actionType=[{params.get("actionType")}] is missing {ex.args} default parameter')

    def __repr__(self):
        return f'{type(self).__name__}: name={self.name}'

    def recoverHistory(self) -> None:
        """
        make a request to the router service for the last point a repeating actionchain visited.
        """
        req = self.routerClient.get(f'/routingcontroller/getLastPage/{self.name}', resp=True, errors=[])
        logging.info(f'{type(self).__name__}::recoverHistory have {req} from routing.')
        return req

    def saveHistory(self) -> None:
        """
        save the the last page the crawler visited.
        """
        pass

    def shouldRun(self) -> bool:
        """
        determine whether or not the chain should run by checking the previous fail flag to stop
        a repeating actionchain and request for errors from nanny service.
        """
        logging.debug(f'Checking if {self.name} should run')
        if self.failedChain:
            return False
        for actionIndex in self.actions:
            logging.debug(f'Checking if {actionIndex} in {self.name} can be run')
            errors = self.nannyClient.get(f'/actionsmanager/findActionErrorReports/{self.name}/{actionIndex}', resp=True, error=[])
            if len(errors) > 0:
                logging.info(f'Will not run {self.name}')
                return False
        return True

    @staticmethod
    def actionFactory(position, actionParams) -> Action:
        """
        Construct an action to execute
        """
        logging.info(f'ActionChain::actionFactory: node=[{position}]: {", ".join(map(lambda key: "{}=[{}]".format(key, actionParams[key]), actionParams))}')
        actionConstructor = ActionTypes.get(actionParams.get('actionType'))
        return actionConstructor(position=position, **actionParams)

    def initialise(self, caller):
        pass

    """
    following methods correspond to module://feed.actiontypes.ActionTypes
    """
    def onClickAction(self, action):
        raise NotImplementedError
    def onInputAction(self, action):
        raise NotImplementedError
    def onPublishAction(self, action):
        raise NotImplementedError
    def onCaptureAction(self, action):
        raise NotImplementedError

    def onChainEnd(self):
        """
        called after the chaions execute method
        """
        logging.info(f'{type(self).__name__}::onChainEnd(): chainName={self.name}')

    def initialiseClients(self):
        logging.info(f'Initialising clients with {self.userID}')
        self.nannyClient.behalf = self.userID
        self.routerClient.behalf = self.userID

    def execute(self, caller, initialise=True):
        self.initialiseClients()
        self.failedChain = False
        if initialise:
            self.initialise(caller)
        for i in range(len(self.actions)):
            self.current_pos = i
            action = self.actions.get(i)
            logging.info(f'ActionChain::execute(): executing action {type(action).__name__}')
            success = Action.execute(self, action)
            if not success:
                logging.info(f'{type(self).__name__}::execute(): Detected failure: actionType={type(action).__name__}, position={i}, name={self.name}. Will go straight to next action. {"Will not re-evaluate" if self.repeating else ""}')
                self.failedChain = True
                continue
            callBackMethod = getattr(caller, f'on{type(action).__name__}Callback')
            for item in success:
                try:
                    callBackMethod(item, chain=self)
                except ActionChainException as ex:
                    logging.warning(f'{type(ex).__name__} raised during on{type(action).__name__}CallBack')
                    ex.chainName = self.name
                    Action.publishActionError(self, ex)
            self.saveHistory()
            self.onChainEnd()

    def getRepublishRoute(self, action):
        logging.debug(f'Getting sample route for {action}. isSample={self.isSample}')
        sample = lambda route: f'{route}-sample'
        name = 'unknown'
        if isinstance(action, CaptureAction):
            name = 'summarizer-route'
        if isinstance(action, PublishAction):
            name = 'worker-route'
        if isinstance(action, ActionChain):
            # TODO: If publisher wants to invoke a chain to be ran, they should set action to be a new action chain object
            name = 'leader-route'
        route = f'{os.getenv("KAFKA_TOPIC_PREFIX", "d")}-{name}'
        logging.info(f'republishing to route=[{route}]')
        if self.isSample:
            return sample(route)
        else:
            return route

    def rePublish(self, action, *args, **kwargs):
        pass







class KafkaChainPublisher(ActionChain):
    pass


class ActionReturnSerialiser(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Tag):
            return str(obj)
        elif isinstance(obj, Action):
            return obj.__dict__()
        else:
            return super().default(obj)


class KafkaActionPublisher(ActionChain):

    flush_rate = os.getenv('PRODUCER_FLUSH_RATE', 30)
    def __init__(self):
        self.producer = KafkaProducer(**kafka_params, value_serializer=lambda m: bytes(json.dumps(m, cls=ActionReturnSerialiser).encode('utf-8')))
        self.messages_out_since_flush = 0

    def rePublish(self, actionReturn, topic):
        self.messages_out_since_flush += 1
        # construct chain parameters to send
        actionReturn.action.data = actionReturn.data
        payload = {
            'actions': [actionReturn.action],
            'startUrl': actionReturn.current_url,
            'isRepeating': False,
            'name': actionReturn.name,
            'userID': actionReturn.userID
        }

        self.producer.send(topic=topic, value=payload)
        logging.info(f'{type(self).__name__}: Republished ActionReturn(startUrl={actionReturn.current_url} for {type(actionReturn.action).__name__} to {topic}')
        # check to see if we should flush
        if self.messages_out_since_flush >= self.flush_rate:
            self.messages_out_since_flush = 0
            logging.info('KafkaActionSubscription::rePublish: flushing messages')
            self.producer.flush()


class ActionChainRunner:

    driver = None
    def __init__(self, implementation, **kwargs):
        logging.info(f'initiated ActionChainRunner fo {type(implementation).__name__}')
        self.implementation = implementation

    def subscription(self):
        pass

    def onClickActionCallback(self, *args, **kwargs):
        logging.info(f'onClickActionCallback')

    def onInputActionCallback(self, *args, **kwargs):
        logging.info(f'onInputActionCallback')

    def onPublishActionCallback(self, *args, **kwargs):
        logging.info(f'onPublishActionCallback')

    def onCaptureActionCallback(self, *args, **kwargs):
        logging.info(f'onCaptureActionCallback')

    def onChainEndCallback(self, chain, chainReturn):
        logging.info(f'onChainEndCallback')

    def renewDriverSession(self):
        pass

    def driverHealthCheck(self):
        pass

    def initialiseCallback(self, *args, **kwargs):
        logging.info('initialiseCallback')

    def main(self):
        killer = GracefulKiller()
        logging.info(f'{type(self).__name__}::main(): beginning subscription poll of kafka')
        for actionChainParams, route in self.subscription():
            # If shutdown was triggered, then do that now
            if killer.kill_now:
                break
            if not self.driverHealthCheck():
                self.renewDriverSession()

            actionChain = self.implementation(driver=self.driver, **actionChainParams)
            if 'sample' in route:
                actionChain.isSample = True
            if not actionChain.shouldRun():
                logging.info(f'Skipping {actionChain.name}.')
                # TODO notifications service here
                continue
            logging.info(f'{type(self).__name__}::main(): START:{actionChain.name} implementing action chain {actionChainParams.get("name")}: {json.dumps(actionChainParams, indent=4)}')
            ret = actionChain.execute(self)
            self.onChainEndCallback(actionChain, ret)
            # should the chain be automatically be re ran from where we are?
            # this can be disabled in the implementation of onChainEndCallback
            while actionChain.repeating and actionChain.shouldRun():
                if killer.kill_now:
                    break
                ret = actionChain.execute(caller=self, initialise=False)
                self.onChainEndCallback(actionChain, ret)
            if killer.kill_now:
                break
            logging.info(f'{type(self).__name__}::main(): END:{actionChain.name} ActionChain::execute() has returned')
        self.cleanUp()

    def cleanUp(self):
        logging.warning(f'ActionChainRunner::cleanUp() No cleanup has been implemented')


class KafkaActionSubscription(ActionChainRunner):

    def __init__(self, *topics,  **kwargs):
        super().__init__(**kwargs)
        self.topics = list(map(KafkaActionSubscription.topic_name, topics))

        logging.info(f'Starting ActionChainRuner type {type(self).__name__}, topics=[{self.topics}], prefix=[{os.environ["KAFKA_TOPIC_PREFIX"]}]')
        self._consumer = KafkaConsumer(**kafka_params, value_deserializer=lambda m: json.loads(m.decode('utf-8')))

    @staticmethod
    def topic_name(topic):
        return  f'{os.environ["KAFKA_TOPIC_PREFIX"]}-{topic}'

    @staticmethod
    def get_route(message):
        return message.topic.split('{os.environ["KAFKA_TOPIC_PREFIX"]}-')[-1]

    def subscription(self):
        self._consumer.subscribe(self.topics)
        for mes in self._consumer:
            route = KafkaActionSubscription.get_route(mes)
            yield mes.value, route


class CommandsActionSubscription(ActionChainRunner):

    def __init__(self, endpoint, actionsImpl):
        super().__init__(actionsImpl)
        self.endpoint = endpoint

    def subscription(self):
        while True:
            actionReq = requests.get(endpoint)
            action = actionReq.json()
            yield action


ActionTypesMap = {
    "ClickAction": ClickAction,
    "InputAction": InputAction,
    "CaptureAction": CaptureAction,
    "PublishAction": PublishAction
}
