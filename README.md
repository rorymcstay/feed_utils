#distributing

##build package:
    python setup.py sdist bdist_wheel

##upload package:
    python3 -m twine upload dist/*

##RoadMap

1. make generic logger
2. unit tests and local testing environment
