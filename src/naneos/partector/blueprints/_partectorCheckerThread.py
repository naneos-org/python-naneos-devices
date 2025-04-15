import time
from threading import Event, Thread

from naneos.logger.custom_logger import get_naneos_logger

logger = get_naneos_logger(__name__)


class PartectorCheckerThread(Thread):
    # from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint

    def __init__(self, partector) -> None:
        super().__init__()
        self.partector = partector

        self._last_message_received = time.time()

        self._stop_event = Event()
        self.start()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        # every 2.1 seconds check if device is still connected
        while not self._stop_event.wait(0.5):
            if time.time() - self._last_message_received < 5:
                continue

            try:
                self.partector._run_check_connection()
            except Exception as e:
                logger.error(e)

    def notify_message_received(self) -> None:
        self._last_message_received = time.time()
