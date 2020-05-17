import logging
import os
import traceback
import requests
import json
from json.encoder import JSONEncoder
from feed.actiontypes import ReturnTypes
from bs4 import BeautifulSoup, Tag
from feed.settings import kafka_params, routing_params
import signal


from kafka import KafkaConsumer, KafkaProducer



class GracefulKiller:
    kill_now = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self,signum, frame):
        self.kill_now = True



class ObjectSearchParams:
    def __init__(self, **kwargs):
        #super().__init__(**kwargs)
        self.isSingle = kwargs.get('isSingle', False)
        self.returnType = kwargs.get('returnType', 'src')
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
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.kwargs = kwargs
        self.css = kwargs.get('css')
        self.xpath = kwargs.get('xpath')
        self.text = kwargs.get('text')
        #self.text = kwargs.get('class')
        self.backup = None

    def _returnItem(self, item, driver):
        logging.debug(f'returning returnType=[{self.returnType}] type for actionType=[{type(self).__name__}]')
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
            formatted = lambda item: item
        elif self.returnType == 'attr':
            formatted = lambda element: element.get_attribute(self.attribute)
        elif self.returnType == 'element':
            formatted = lambda item: item
        logging.debug(f'ObjectSearchParams::_returnItem(): returning {len(item)}.')
        return list(map(formatted, item)) if len (item) > 1 else formatted(item[0])

    def search(self, driver):

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


class Action(BrowserSearchParams):

    def __init__(self, position, **kwargs):
        super().__init__(**kwargs)
        self.kwargs = kwargs
        self.position = position

    @staticmethod
    def execute(chain, action):
        actionType = type(action).__name__
        try:
            ret = getattr(chain, f'on{actionType}')(action)
            logging.debug(f'Action::execute: Action executed succesfully, name=[{chain.name}], position=[{action.position}]')
            return ret
        except Exception as ex:
            traceback.print_exc()
            logging.warning(f'Action::execute:: {type(ex).__name__} thrown whilst processing name=[{chain.name}], position=[{action.position}], args=[{ex.args}]')
            return False
            # TODO Exception reporting callback called here
            # OnClickException for example

    def getActionableItem(self, action, driver):
        item = self.search(driver)
        logging.info(f'{type(self).__name__}::getActionableItem: have num_items=[{ 1 if not isinstance(item, list) else len(item)}]')
        return item

    @staticmethod
    def get_params():
        # TODO For UI-Server
        return [self.__dict__().keys()]


class CaptureAction(Action):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.kwargs.pop('data', None)
        self.kwargs.pop('src', None)
        self.returnType = 'src'
        self.captureName = kwargs['captureName'] # mandatory
        self.data = kwargs.get('data', None)

    def __dict__(self):
        return dict(data=self.data, **self.kwargs)

class InputAction(Action):

    def __init__(self, inputString, **kwargs):
        super().__init__(**kwargs)
        self.insputString = inputString
        self.isSingle = True
        self.returnType = 'element'

    def __dict__(self):
        return dict(inputString=self.insputString, **self.kwargs)

class PublishAction(Action):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.urlStub = kwargs.get('urlStub')

    def __dict__(self):
        return dict(url=self.url, urlStub=self.urlStub, **self.kwargs)

class ClickAction(Action):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.isSingle = True
        self.returnType = 'element'

ActionTypes = {
    "ClickAction": ClickAction,
    "InputAction": InputAction,
    "CaptureAction": CaptureAction,
    "PublishAction": PublishAction
}

class ActionChain:
    actions= {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.name = kwargs.get('name')
        self.startUrl = kwargs.get('startUrl')
        self.repeating = kwargs.get('isRepeating', True)
        actionParams = kwargs.get('actions', [])
        self.failedChain = False
        for order, params in enumerate(actionParams):
            try:
                action = ActionChain.actionFactory(position=order, actionParams=params)
                self.actions.update({order: action})
            except KeyError as ex:
                # TODO: wAt this point we should pass this onto the user
                traceback.print_exc()
                logging.error(f'{type(self).__name__}::__init__(): chainName=[{self.name}], position=[{order}] actionType=[{params.get("actionType")}] is missing {ex.args} default parameter')


    def recoverHistory(self):
        try:
            req = requests.get('http://{host}:{port}/routingcontroller/getLastPage/{name}'.format(name=self.name, **routing_params))
        except Exception as e:
            logging.warning(f'ActionChain::recoverHistory: router is unavailable')
        logging.info(f'{type(self).__name__}::recoverHistory have {req} from routing.')
        try:
            data = req.json()
        except Exception:
            logging.warning(f'Did not get valid response from router. response=[{req}]')
        return data

    def saveHistory(self, url):
        pass

    @staticmethod
    def actionFactory(position, actionParams):
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

    def execute(self, caller, initialise=True):
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
                callBackMethod(item)
            self.saveHistory()
            self.onChainEnd()

    def getRepublishRoute(self, action):
        name = 'unknown'
        if isinstance(action, CaptureAction):
            name = 'summarizer-route'
        if isinstance(action, PublishAction):
            name = 'worker-route'
        if isinstance(action, ActionChain):
            # TODO: If publisher wants to invoke a chain to be ran, they should set action to be a new action chain object
            name = 'leader-route'
        return f'{os.getenv("KAFKA_TOPIC_PREFIX", "d")}-{name}'

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

    def rePublish(self, actionReturn):
        self.messages_out_since_flush += 1
        topic = self.getRepublishRoute(actionReturn.action)
        # construct chain parameters to send
        actionReturn.action.data = actionReturn.data
        payload = {
            'actions': [actionReturn.action],
            'startUrl': actionReturn.current_url,
            'isRepeating': False,
            'name': actionReturn.name
        }

        self.producer.send(topic=topic, value=payload)
        logging.info(f'{type(self).__name__}::rePublish(): Republished ActionReturn(startUrl={actionReturn.current_url} for {type(actionReturn.action).__name__} to {topic}')
        # check to see if we should flush
        if self.messages_out_since_flush >= self.flush_rate:
            self.messages_out_since_flush = 0
            logging.info('KafkaActionSubscription::rePublish: flushing messages')
            self.producer.flush()


class ActionChainRunner:

    driver = None
    def __init__(self, implementation, **kwargs):
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
        for actionChainParams in self.subscription():
            if not self.driverHealthCheck():
                self.renewDriverSession()
            if killer.kill_now:
                self.cleanUp()
                logging.info(f'cleaned up resources')
                break
            actionChain = self.implementation(driver=self.driver, **actionChainParams)
            logging.info(f'{type(self).__name__}::main(): START:{actionChain.name} implementing action chain {actionChainParams.get("name")}: {json.dumps(actionChainParams, indent=4)}')
            ret = actionChain.execute(self)
            self.onChainEndCallback(actionChain, ret)
            # should the chain be automatically be re ran from where we are?
            # this can be disabled in the implementation of onChainEndCallback
            while actionChain.repeating and not actionChain.failedChain:
                actionChain.execute(caller=self, initialise=False)
            logging.info(f'{type(self).__name__}::main(): END:{actionChain.name} ActionChain::execute() has returned')

    def cleanUp(self):
        logging.warning(f'ActionChainRunner::cleanUp() No cleanup has been implemented')


class KafkaActionSubscription(ActionChainRunner):

    def __init__(self, topic,  **kwargs):
        super().__init__(**kwargs)
        self._consumer = KafkaConsumer(**kafka_params, value_deserializer=lambda m: json.loads(m.decode('utf-8')))
        self._consumer.subscribe([f'{os.getenv("KAFKA_TOPIC_PREFIX")}-{topic}'])

    def subscription(self):
        for mes in self._consumer:
            yield mes.value


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
