import os

kafka_params = {
    "bootstrap_servers": [os.getenv("KAFKA_ADDRESS", "localhost:29092")],
}

browser_params = {
    "internal_port":  4444,
    "host": os.getenv("BROWSER_CONTAINER_HOST", None),
    "image": os.getenv('BROWSER_IMAGE', 'selenium/standalone-chrome:3.141.59'),
    "base": os.getenv('BROWSER_BASE_PORT', 4444),
    "max": os.getenv("MAX_FEEDS", 10),
    "base_port": os.getenv("BROWSER_BASE_PORT", 4444)
}

routing_params = {
    "host": os.getenv("ROUTER_HOST", "localhost"),
    "port": os.getenv("FLASK_PORT", 5002),
    "api_prefix": "routingcontroller"
}

nanny_params = {
    "host": os.getenv("NANNY_HOST", "localhost"),
    "port": os.getenv("FLASK_PORT", 5003),
    "api_prefix": "containercontroller",
    "params_manager": "parametercontroller"
}

hazelcast_params = {
    "host": os.getenv("HAZELCAST_HOST", "localhost"), "port": os.getenv("HAZELCAST_PORT", 5701)
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
    "database": os.getenv("DATABASE_NAME", "postgres"),
    "user": os.getenv("DATABASE_USER", "postgres"),
    "password": os.getenv("DATABASE_PASS", "postgres"),
}

feed_params = {
    "image": os.getenv("LEADER_TEMPLATE"),
    "success": os.getenv("LEADER_START", "feed has started"),
    "base_port": int(os.getenv("LEADER_BASE_PORT", 9000))
}

retry_params = {
    "times": 10,
    "wait": 10
}

class BrowserConstants:
    CONTAINER_TIMEOUT = int(os.getenv('CONTAINER_TIMEOUT', 10))
    CONTAINER_SUCCESS = 'Selenium Server is up and running on port'
    CONTAINER_QUIT = "Shutdown complete"
    client_connect = 'wd/hub'
    worker_timeout = int(os.getenv('WORKER_TIMEOUT', '3'))
