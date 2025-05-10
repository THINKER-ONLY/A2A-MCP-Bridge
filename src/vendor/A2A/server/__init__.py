# This file makes 'Adapter/src/vendor/A2A/server' a package.
# It exports A2AServer from the vendored server.py file,
# and TaskManager/InMemoryTaskManager from the vendored task_manager.py file.

from .server import A2AServer
from .task_manager import TaskManager, InMemoryTaskManager 