"""Package initialization for nomon."""

__version__ = "0.2.0"
__author__ = "Perceptua"

from .camera import Camera
from .protocol import (
    CommandMessage,
    MessageHandler,
    NotificationMessage,
    ResponseMessage,
)

try:
    from .streaming import StreamServer
    __all__ = [
        "Camera",
        "StreamServer",
        "CommandMessage",
        "ResponseMessage",
        "NotificationMessage",
        "MessageHandler",
    ]
except ImportError:
    # Flask not installed, streaming not available
    __all__ = [
        "Camera",
        "CommandMessage",
        "ResponseMessage",
        "NotificationMessage",
        "MessageHandler",
    ]

