"""Package initialization for nomon."""

__version__ = "0.1.0"
__author__ = "Perceptua"

from .camera import Camera
from .updater import UpdateManager

try:
    from .streaming import StreamServer
    from .telemetry import TelemetryPublisher

    __all__ = ["Camera", "StreamServer", "TelemetryPublisher", "UpdateManager"]
except ImportError:
    try:
        from .streaming import StreamServer

        __all__ = ["Camera", "StreamServer", "UpdateManager"]
    except ImportError:
        try:
            from .telemetry import TelemetryPublisher

            __all__ = ["Camera", "TelemetryPublisher", "UpdateManager"]
        except ImportError:
            __all__ = ["Camera", "UpdateManager"]
