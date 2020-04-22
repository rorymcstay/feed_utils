import logging

from selenium.webdriver.remote.webdriver import WebDriver

ReturnTypes = ['text', 'src', 'attr', 'element']


class ObjectSearchParams():
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.css = kwargs.get('css')
        self.xpath = kwargs.get('xpath')
        self.text = kwargs.get('text')
        self.text = kwargs.get('class')
        self.isSingle = kwargs.get('isSingle', False)
        self.returnType = kwargs.get('returnType')
        self.attribute = kwargs.get('attribute')
        self.backup = None

    def __dict__(self):
        return self.kwargs

    def verifyResultLength(self, items):
        if len(items) == 0:
            return False
        if isSingle and len(items) > 1:
            self.backup = items
            return False
        else:
            return True

    def returnItem(self, item, driver):
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
        elif self.returnTyp == 'element':
            formatted = lambda item: item
        return list(map(formatted, item)) if len (item) > 1 else formatted(item[0])

    def search(self, driver: WebDriver):
        ret = driver.find_elements_by_css_selector(self.css)
        if self.verifyResultLength(ret):
            return self.returnItem(item)
        ret = driver.find_elements_by_xpath(self.xpath)
        if self.verifyResultLength(item):
            return self.returnItem(ret)
        if self.backup:
            return self.returnItem([self.backup[0]])
        else:
            return None


class Action:
    objectSearchParms = ObjectSearchParams()

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.objectSearchParms = ObjectSearchParams(**kwargs.get('objectSearchParms'))

    @staticmethod
    def execute(chain, action):
        actionType = type(action).__name__
        getattr(chain, f'on{actionType}')()

    @staticmethod
    def getActionableItem(action, driver):
        return self.objectSearchParms.search(driver)


class CaptureAction(Action):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.objectSearchParms.returnType = 'src'

    def __dict__(self):
        return dict(actionType='CaptureAction', url=self.url, **self.kwargs)

class InputAction(Action):

    def __init__(self, inputString, **kwargs):
        super().__init__(**kwargs)
        self.insputString = inputString
        self.objectSearchParms.returnType = 'element'

    def __dict__(self):
        return dict(actionType='InputAction', inputString=self.insputString, **self.kwargs)

class PublishAction(Action):
    def __init__(self, url, urlStub, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.urlStub = urlStub

    def __dict__(self):
        return dict(actionType='PublishAction', url=self.url, urlStub=self.urlStub, **self.kwargs)

class ClickAction(Action):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.objectSearchParms.returnType = 'element'

    def __dict__(self):
        return dict(actionType='CaptureAction', **self.kwargs)


ActionTypes = {
    "ClickAction": ClickAction,
    "InputAction": InputAction,
    "CaptureAction": CaptureAction,
    "PublishAction": PublishAction
}

BaseActionParams = {
    "objectSearchParms": {
        "css": None,
        "xpath": None,
        "text": None,
        "isSingle": false,
        "returnType": 'src'
    }
}


class ActionChain:
    actions= {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.name = kwargs.get('name')
        self.repeating = kwargs.get('repeating')

        for key in kwargs:
            action = ActionChain.actionFactory(**kwargs.get(key))
            self.actions.update({key: action})

    def recoverHistory(self):
        req = requests.get('http://{host}:{port}/routincontroller/getLastPage/{name}'.format(name=self.name, **routing_params))
        data = req.json()
        return data.get('url')

    def saveHistory(self, url):
        pass

    @staticmethod
    def actionFactory(actionParams):
        actionConstructor = ActionTypes.get(actionParams.get('actionType'))
        return actionConstructor(**actionParams)

    def initialise(self):
        pass

    """
    following methods correspon to ActionTypes
    """
    def onClickAction(self, action):
        logging.warning(f'{type(self).__name__}::on{type(action).__name__} not implemented')
        pass
    def onInputAction(self, action):
        logging.warning(f'{type(self).__name__}::on{type(action).__name__} not implemented')
        pass
    def onPublishAction(self, action):
        logging.warning(f'{type(self).__name__}::on{type(action).__name__} not implemented')
        pass
    def onCaptureAction(self, action):
        logging.warning(f'{type(self).__name__}::on{type(action).__name__} not implemented')
        pass

    def execute(self, initialise=True):
        if initialise:
            self.initialise()
        for i in range(len(self.actions)):
            self.current_pos = i
            action = self.actions.get(i)
            logging.info(f'executing action {type(action).__name__}')
            Action.execute(self, action)
            self.saveHistory()
        if self.repeating:
            self.execute(initialise=False)

    def getRepublishRoute(self, action):
        if action.objectSearchParms.returnType == 'src' and isinstance(action, CaptureAction):
            return 'summarizer-route'
        if action.get('trial'):
            #TODO sample aid for src in ui
            return f'trialActions/{self.name}/{self.current_pos}'
        if action.objectSearchParms.returnType == 'attr' and isinstance(action, PublishAction):
            return 'worker-route'
        if isinstance(action, ActionChain):
            return 'leader-route'

    def rePublish(action, data):
        pass


class KafkaActionPublisher(ActionChain):

    def __init__(self):
        self.producer = KafkaProducer(**kafka_params)

    def rePublish(self, key, action, data):
        topic = self.getRepublishRoute(action)
        if isinstance(data, list):
            i = 0
            for item in data:
                i += 1
                self.producer.send(topic=topic, key=bytes(f'{key}_{i}', 'utf-8'), value=json.dumps(dict(action=action.__dict__(), data=item)).encode('utf-8'))
            logging.info(f'republished {len(data)} items for {key} for {type(action).__name__} to {topic}')
        else:
            self.producer.send(topic=topic, key=bytes(key, 'utf-8'), value=json.dumps(dict(action=action.__dict__(), item=item)).encode('utf-8'))
            logging.info(f'republished {key} for {type(action).__name__} to {topic}')


class ActionChainRunner:

    def __init__(self, implementation, **kwargs):
        self.implementation = implementation

    def subscription(self):
        pass

    def main(self):
        for actionChainParams in self.subscription():
            actionChain = self.implementation(actionChainParams)
            actionChain.execute()


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

