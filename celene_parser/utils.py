
import os
import platform as sys_platform
from typing import Any


# Configuration
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'


def logger(content: Any):
    """Logger function - only prints if DEBUG is True"""
    if DEBUG:
        print(str(content))


# Service endpoints pour CAS
CAS_SERVICE_ENUM = {
    "Celene": "https%3A%2F%2Fcelene.insa-cvl.fr%2Flogin%2Findex.php"
}
