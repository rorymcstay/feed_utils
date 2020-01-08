#distributing

##build package:
    python setup.py sdist bdist_wheel

##upload package:
    python3 -m twine upload dist/*


