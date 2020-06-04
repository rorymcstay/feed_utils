import os

# service params

kafka_params = {
    "bootstrap_servers": [os.getenv("KAFKA_ADDRESS", "localhost:29092")],
}

browser_params = {
    "internal_port":  4444,
    "host": os.getenv("BROWSER_CONTAINER_HOST", 'localhost'),
    "image": os.getenv('BROWSER_IMAGE', 'selenium/standalone-chrome:3.141.59'),
    "port": os.getenv('BROWSER_PORT', 4444),
    "max": os.getenv("MAX_FEEDS", 10),
    "base_port": os.getenv("BROWSER_BASE_PORT", 4444)
}


mongo_params = {
    "host": os.getenv("MONGO_HOST", "localhost:27017"),
    "username": os.getenv("MONGO_USER", "root"),
    "password": os.getenv("MONGO_PASS", "root"),
    "serverSelectionTimeoutMS": 5
}

database_parameters = {
    "host": os.getenv("DATABASE_HOST", "localhost"),
    "port": os.getenv("DATABASE_PORT", 5432),
    "database": os.getenv("DATABASE_NAME", "feeds"),
    "user": os.getenv("DATABASE_USER", "feeds"),
    "password": os.getenv("DATABASE_PASS", "postgres"),
}

authn_params = {
    'authn_url': os.getenv('AUTHN_SERVER', 'http://localhost:8080'),
    'authn_pass': os.getenv('AUTHN_PASS', 'world'),
    'authn_user': os.getenv('AUTHN_USER', 'hello')
}


########################
# COMPONENT Connectivity
# defaults to localhost for local debugging
# ports here should match up with the development.yml for exposing ports
nanny_params = {
    "host": os.getenv("NANNY_HOST", "localhost"),
    "port": os.getenv("FLASK_PORT", 5003), # nanny
    "api_prefix": "containercontroller",
    "params_manager": "parametercontroller"
}

routing_params = {
    "host": os.getenv("ROUTER_HOST", "localhost"),
    "port": os.getenv("FLASK_PORT", 5002), # routing
    "api_prefix": "routingcontroller"
}

########################


# settings

retry_params = {
    "times": 10,
    "wait": 10
}

feed_params = {
    "image": os.getenv("LEADER_TEMPLATE"),
    "success": os.getenv("LEADER_START", "feed has started"),
    "base_port": int(os.getenv("LEADER_BASE_PORT", 9000))
}

logger_settings_dict = lambda name: {
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s]%(thread)d: %(module)s - %(levelname)s - %(message)s |%(filename)s:%(lineno)d',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'kafka': {
        'level': os.getenv("KAFKA_LOG_LEVEL", 'WARNING')
    },
    name: {
        'level': os.getenv("LOG_LEVEL", "INFO"),
        'handlers': ['wsgi']
    },
    'urllib3': {
        'level': os.getenv('URLLIB_LOG_LEVEL', 'WARNING')
    },
    'selenium': {
        'level': os.getenv('SELENIUM_LOG_LEVEL', 'INFO')
    }
}

