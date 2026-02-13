"""Package initialization for nomon."""

__version__ = "0.1.0"
__author__ = "Perceptua"

from .camera import Camera

try:
    from .streaming import StreamServer
    __all__ = ["Camera", "StreamServer"]
except ImportError:
    # Flask not installed, streaming not available
    __all__ = ["Camera"]


