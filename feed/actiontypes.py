ReturnTypes = ['text', 'src', 'attr', 'element']

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
        self.chainName = chainName
        self.actionHash = actionHash
        self.message = kwargs.get('message', '')

    def __dict__(self):
        return dict(position=self.position, actionHash=self.actionHash, chainName=self.chainName, errorType=type(self).__name__, message=self.message)

class ActionableItemNotFound(ActionChainException):
    pass

class ActionableItemNotInteractable(ActionChainException):
    pass

class NeedsMappingWarning(ActionChainException):
    pass
