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

    def _verifyResultLength(self, items) -> bool:
        """
        check the number of found items is correct, if there are too many items,
        the items are stored as a backup.
        """
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
        """
        :params: css of the item
        :params: xpath of item
        :params: text of item
        """
        super().__init__(**kwargs)
        self.kwargs = kwargs
        self.css = kwargs.get('css')
        self.xpath = kwargs.get('xpath')
        self.text = kwargs.get('text')
        #self.class = kwargs.get('class') 
        # TODO increase number of possible params 
        # larger scale feature to offer more range of 
        # options for viewing source (e.g: raw html source and side by side page) in ui where 
        # user can specify things on lower level
        self.backup = None # backup is set if _verifyResultLength returns incorrect number of items.

    def _returnItem(self, item: WebElement, driver: WebDriver): # -> ReturnItem
        """
        given a located element of the page, and the caller's webdriver, return the item
        in a representation dependent on the
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
        """
        Find the element of the page, given the parameters.
        object is searched in conjunction with'_verifyResultLength' in
        order of parameters.

        TODO: make the order configurable - not necessarily to the user but
        to the running environment
        """

        # first try css selector
        logging.info(f'{type(self).__name__}::search(driver): searching for elemnent with css=[{self.css}]' ) # we need to stop typing function names, makes grep awful
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

        # then try backup with text. backup is set in ObjectSearchParams::_verifyResultLength(items)
        if self.backup:
            for res in filter(lambda item: item.text.upper() == self.text, self.backup):
                logging.debug(f'using element [{ret}] from backup')
                return self._returnItem([ret], driver)
            return self._returnItem([self.backup[0]], driver)
        else:
            # TODO brute search with text at this point
            return None


class Action(BrowserSearchParams):

    """
    Base action class
    """
    def __init__(self, position, **kwargs):
        super().__init__(**kwargs)
        self.kwargs = kwargs
        self.position = position

    def getActionHash(self):
        return hashlib.md5(f'{type(self).__name__}:{self.position}:{self.css}:{self.xpath}'.encode('utf-8')).hexdigest()

    @staticmethod
    def execute(chain: ActionChain, action):
        """
        Call the actionchains execute method for this action type
        TODO: This should really be moved to the action chain itself, so actions run
        through the chain.
        """
        actionType = type(action).__name__
        try:
            ret = getattr(chain, f'on{actionType}')(action)
            logging.debug(f'Action::execute: Action executed succesfully, name=[{chain.name}], position=[{action.position}]')
            return ret
        except ActionChainException as ex:
            Action.publishActionError(chain, ex)
            logging.info(f'{type(ex).__name__} thrown whilst processing')
            return False
        except Exception as ex:
            traceback.print_exc()
            logging.warning(f'Action::execute:: {type(ex).__name__} thrown whilst processing name=[{chain.name}], position=[{action.position}], args=[{ex.args}]')
            Action.publishUnhandledActionError(chain, ex, action)
            return False
            # TODO Exception reporting callback called here
            # OnClickException for example

    def getActionableItem(self, action, driver):
        """
        just a wrapper, probably pointless
        """
        item = self.search(driver)
        # TODO this should be overriden by specifc action implementation.
        # heck, it could even be user python code working on a ReturnType.
        # Could then be used to enact user defined python code on the 
        # html string of the entire webpage. Just need to have the types
        # in place.
        logging.info(f'{type(self).__name__}::getActionableItem: have num_items=[{ 1 if not isinstance(item, list) else len(item)}]')
        return item

    @staticmethod
    def get_params():
        # TODO For UI-Server
        return [self.__dict__().keys()]

    @staticmethod
    def publishActionError(chain, actionException):
        actionException.userID = chain.nannyClient.behalf
        chain.nannyClient.put(f'/actionsmanager/reportActionError/{actionException.chainName}', payload=actionException.__dict__())

    @staticmethod
    def publishUnhandledActionError(chain, exception, action):
        """
        publish undefined error in running of action, i.e an exception
        not derived from ActionChainException
        """
        #chain.nannyClient.put(f'')
        # TODO 
        logging.warning(f'Unhandled exception in action {action.__dict__()}, exception={exception.args}')
        pass


class CaptureAction(Action):
    def __init__(self, **kwargs):
        """
        :param: returnType: I dont see why this should be a parameter!!! should change for simplicity
        :param: parentAttributes: this parameter is not user provided. it is enriched between components (provided by upstream)
        :param: name of the data item, eg. cars
        :param: data, provided by upstream
        :param: backupKey: if no unique identifier is found within the set of results, what to save it as (eg. if no url is found),
        """
        super().__init__(**kwargs)
        self.returnType = self.kwargs.pop('returnType', 'src')
        self.parentAttributes = self.kwargs.pop('parentAttributes', {})
        # webcralwer adds the attributes of the parent of the html tag to the parser, incase it contains a link. you can probably tell... a hack
        self.captureName = self.kwargs.pop('captureName') # mandatory
        self.data = self.kwargs.pop('data', None)
        self.backupKey = self.kwargs.pop('backupKey', None) # TODO: this could remove the hack of the parentAttributes if done correctly

    def __dict__(self):
        return dict(data=self.data, parentAttributes=self.parentAttributes, backupKey=self.backupKey, captureName=self.captureName, returnType=self.returnType, **self.kwargs)

class InputAction(Action):

    def __init__(self, inputString, **kwargs):
        super().__init__(**kwargs)
        self.insputString = inputString
        self.isSingle = True
        self.returnType = 'element'

    def __dict__(self):
        return dict(inputString=self.insputString, **self.kwargs)

class PublishAction(Action):
    """
    TODO: Functionality still yet to be fully tested and implemented
    intended purpose is to trigger another action chain. so this would
    be the link to that actionchain lookup ultimatley. all it will
    need is parameters from nanny. That way users can reuse actionchains
    for example a login action chain followed by a list of different actionchains.
    """
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



ReturnTypes = [ # This isn't used so should be implmented properly by type system.
    # each Action type expects the ObjectSearchParams::search to return a spec
    'text', # return the text within the tags
    'src', # get the src of the html tags. <Tag ... /> in string format
    'attr', # get an attribute from the tag.
    'element' # return a WebElement
    # TODO: make this into a class hiearchy or ReturnType -> TextReturnType
]

ActionTypes = [
    "ClickAction",
    "InputAction",
    "CaptureAction",
    "PublishAction"
]


def get_mandatory_params(actionType):
    paramsMap = dict(Action=["css","xpath","text","isSingle", "actionType"],
                     CaptureAction=['captureName'],
                     ClickAction=[],
                     InputAction=['inputString'],
                     PublishAction=['urlStub'])
    return list(set(paramsMap.get('Action') + paramsMap.get(actionType, [])))

class ActionChainException(Exception):

    def __init__(self, position=None, chainName=None, actionHash=None, **kwargs):
        self.position = position
        self.userID = kwargs.get('userID')
        self.chainName = chainName
        self.actionHash = actionHash
        self.message = kwargs.get('message', '')

    def __dict__(self):
        return dict(userID=self.userID, position=self.position, actionHash=self.actionHash, chainName=self.chainName, errorType=type(self).__name__, message=self.message)

class ActionableItemNotFound(ActionChainException):
    pass

class ActionableItemNotInteractable(ActionChainException):
    pass

class NeedsMappingWarning(ActionChainException):
    pass
