from unittest import TestCase
from flask_classy import route

from feed.testutils import DocumentationTest

example1 = {
    "request": "/getFeeds/",
    "response": '["donedeal","pistonheads"]'
}

example2 = {
    "request": "/getFeeds/",
    "payload": '{"key":"value"}',
    "response": '["donedeal","pistonheads"]'
}


@route(rule="/a/partial/url/<params:string>", methods=['GET', 'POST'], other='somethingelse')
def getFeeds(string):
    """
    <example1>
        #request: /getFeeds/case1
        #response: ["donedeal", "pistonheads"]
    <example1/>

    <example2>
        #request: /getFeeds/case2
        #payload: {"key": "value"}
        #response: ["donedeal", "pistonheads"]
    <example2/>

    :return:
    """
    pass


class TestDocumentationTest(TestCase):
    def test__test_case_regex(self):
        regex = DocumentationTest._testCaseRegex('exampleName')
        # self.assert_(isinstance(regex,  _sre.SRE_Pattern))
        self.assertTrue(regex.pattern == '(<exampleName>|<exampleName/>)')

    def test_getValidMethods(self):
        docTest = DocumentationTest(getFeeds)
        mets = docTest.getValidMethods()
        self.assertListEqual(mets, ['GET', 'POST'], msg='list of methods do not match')

    def test_get_test_clauses(self):
        docTest = DocumentationTest(getFeeds)

        # request and response can be parsed
        mets = docTest.getTestClauses('example1')
        self.assertDictEqual(mets, example1)

        # optionally payload may be parsed
        # TODO parse json in this method
        mets = docTest.getTestClauses('example2')
        self.assertDictEqual(mets, example2)

    def test_get_names(self):
        docTest = DocumentationTest(getFeeds)
        names = docTest.getNames()
        self.assertListEqual(['example1', 'example2'], names)

    def test_generate(self):
        er = DocumentationTest.generate(getFeeds)
        self.assertDictEqual(er.cases, {'/getFeeds/case1': {
                                            'response': '["donedeal","pistonheads"]'
                                        },
                                        '/getFeeds/case2': {
                                            'response': '["donedeal","pistonheads"]',
                                            'payload': '{"key":"value"}'}
                                        })
        # TODO case where there are multiple cases for a method with no params
