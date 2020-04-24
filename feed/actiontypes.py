ReturnTypes = ['text', 'src', 'attr', 'element']

ActionTypes = [
    "ClickAction",
    "InputAction",
    "CaptureAction",
    "PublishAction"
]

BaseActionParams = {
    "objectSearchParms": {
        "css": None,
        "xpath": None,
        "text": None,
        "isSingle": False,
        "returnType": 'src'
    }
}

