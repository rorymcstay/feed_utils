ReturnTypes = ['text', 'src', 'attr', 'element']

ActionTypes = [
    "ClickAction",
    "InputAction",
    "CaptureAction",
    "PublishAction"
]


def get_mandatory_params(actionType):

    paramsMap = dict(Action=["css","xpath","text","isSingle"],
                     CaptureAction=['captureName']
                     ClickAction=[],
                     InputAction=['inputString'],
                     PublishAction=[])
    return list(set(paramsMap.get('Action') + paramsMap.get(actionType))))


