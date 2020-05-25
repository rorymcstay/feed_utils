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

    def __init__(self, position, chainName, actionHash):
        self.position = position
        self.chainName = chainName
        self.actionHash = actionHash

    def __dict__(self):
        return dict(position=self.position, actionHash=self.actionHash, chainName=self.chainName, errorType=type(self).__name__)

class ActionableItemNotFound(ActionChainException):
    pass

class ActionableItemNotInteractable(ActionChainException):
    pass

