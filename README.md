#distributing


##build package (from venv):

python setup.py sdist bdist_wheel

##upload package (from sys):

python3 -m twine upload dist/*

##RoadMap


1. make generic logger
2. unit tests and local testing environment
