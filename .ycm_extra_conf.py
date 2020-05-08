import os


def Settings( **kwargs ):
    return {
        'interpreter_path': f'{os.getcwd()}/venv/bin/python',
        'sys_path': "{}/utils".format(os.getenv('SOURCE_DIR', f'{os.getcwd()}/../'))
    }
