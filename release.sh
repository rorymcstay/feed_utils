rm -r feed_utils.* build dist

source venv/bin/activate
python setup.py sdist bdist_wheel

/usr/bin/python3 -m twine upload dist/* 
