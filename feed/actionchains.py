import logging
import requests
import json
from feed.actiontypes import ReturnTypes
from feed.settings import kafka_params, routing_params

from kafka import KafkaConsumer, KafkaProducer


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
        self.text = kwargs.get('class')
        self.backup = None

    def _returnItem(self, item, driver):
        if self.returnType == 'text':
            formatted = lambda item: item.text
        elif self.returnType == 'src':
            classes = set([element.get_attribute('class') for element in item])
            soup = BeautifulSoup(driver.page_source)
            out = []
            for cls in classes:
                out.extend(soup.findAll(attrs={'class': cls}))
            formatted = lambda item: str(item)
        elif self.returnType == 'attr':
            formatted = lambda element: element.get_attribute(self.attribute)
        elif self.returnType == 'element':
            formatted = lambda item: item
        return list(map(formatted, item)) if len (item) > 1 else formatted(item[0])

    def search(self, driver):
        ret = driver.find_elements_by_css_selector(self.css)
        # first try css selector
        if self._verifyResultLength(ret):
            logging.debug(f'found element [{ret}] with css')
            return self._returnItem(ret, driver)
        ret = driver.find_elements_by_xpath(self.xpath)
        # then try xpath
        if self._verifyResultLength(ret):
            logging.debug(f'found element [{ret}] with xpath')
            return self._returnItem(ret, driver)
        # if one item was meant to be retured, just take first item in list.
        # TODO: should search backup list with text at this point
        if self.backup:
            logging.debug(f'using element [{ret}] from backup')
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
            logging.debug(f'{actionType} has returned succesfully, name=[{chain.name}], position=[{action.position}]')
            return ret
        except Exception as ex:
            logging.warning(f'{type(ex).__name__} thrown whilst processing name=[{chain.name}], position=[{action.position}], args=[{ex.args}]')
            return False
            # TODO Exception reporting callback called here
            # OnClickException for example

    def getActionableItem(self, action, driver):
        item = self.search(driver)
        logging.info(f'have item=[{item}], length=[{ 1 if not isinstance(item, list) else len(item)}]')
        return item

    @staticmethod
    def get_params():
        # TODO For UI-Server
        return []


class CaptureAction(Action):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.returnType = 'src'
        self.data = kwargs.get('data', None)

    def __dict__(self):
        return dict(actionType='CaptureAction', **self.kwargs)

class InputAction(Action):

    def __init__(self, inputString, **kwargs):
        super().__init__(**kwargs)
        self.insputString = inputString
        self.isSingle = True
        self.returnType = 'element'

    def __dict__(self):
        return dict(actionType='InputAction', inputString=self.insputString, **self.kwargs)

class PublishAction(Action):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.url = kwargs.get('url')
        self.urlStub = kwargs.get('urlStub')

    def __dict__(self):
        return dict(actionType='PublishAction', url=self.url, urlStub=self.urlStub, **self.kwargs)

class ClickAction(Action):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.isSingle = True
        self.returnType = 'element'

    def __dict__(self):
        return dict(actionType='CaptureAction', **self.kwargs)

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
        actionParams = kwargs.get('actions')
        self.failedChain = False
        for order, params in enumerate(actionParams):
            action = ActionChain.actionFactory(position=order, actionParams=params)
            self.actions.update({order: action})

    def recoverHistory(self):
        req = requests.get('http://{host}:{port}/routingcontroller/getLastPage/{name}'.format(name=self.name, **routing_params))
        logging.info(f'have {req} from routing.')
        data = req.json()
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

    def execute(self, caller, initialise=True):
        self.failedChain = False
        if initialise:
            self.initialise(caller)
        for i in range(len(self.actions)):
            self.current_pos = i
            action = self.actions.get(i)
            logging.info(f'executing action {type(action).__name__}')
            success = Action.execute(self, action)
            if not success:
                logging.info(f'Detected failure: actionType={type(action).__name__}, position={i}, name={self.name}. Will go straight to next action. {"Will not re-evaluate" if self.repeating else ""}')
                self.failedChain = True
                continue
            callBackMethod = getattr(caller, f'on{type(action).__name__}Callback')
            for item in success:
                callBackMethod(item)
            self.saveHistory()
        if self.repeating and not self.failedChain:
            self.execute(caller, initialise=False)

    def getRepublishRoute(self, action):
        if isinstance(action, CaptureAction):
            return 'summarizer-route'
        if isinstance(action, PublishAction):
            return 'worker-route'
        if isinstance(action, ActionChain):
            # TODO: If publisher wants to invoke a chain to be ran, they should set action to be a new action chain object
            return 'leader-route'

    def rePublish(self, action, *args, **kwargs):
        pass


class KafkaChainPublisher(ActionChain):
    pass


class KafkaActionPublisher(ActionChain):

    def __init__(self):
        self.producer = KafkaProducer(**kafka_params, value_serializer=lambda m: bytes(json.dumps(m).encode('utf-8')))

    def rePublish(self, actionReturn):
        topic = self.getRepublishRoute(actionReturn.action)
        self.producer.send(topic=topic, value=actionReturn.__dict__())
        logging.debug(f'republished items for {type(actionReturn.action).__name__} to {topic}')


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

    def initialiseCallback(self, *args, **kwargs):
        logging.info('initialiseCallback')

    def main(self):
        for actionChainParams in self.subscription():
            logging.debug(f'implementing action chain {actionChainParams.get("name")}: {json.dumps(actionChainParams, indent=4)}')
            actionChain = self.implementation(driver=self.driver, **actionChainParams)
            ret = actionChain.execute(self)


class KafkaActionSubscription(ActionChainRunner):

    def __init__(self, topic,  **kwargs):
        super().__init__(**kwargs)
        self._consumer = KafkaConsumer(**kafka_params, value_deserializer=lambda m: json.loads(m.decode('utf-8')))
        self._consumer.subscribe([topic])

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

