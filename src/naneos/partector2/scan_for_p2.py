from naneos.serial_utils import list_serial_ports as ls_ports
from naneos.partector2 import Partector2

from threading import Thread
from queue import Queue


def scan_for_serial_partector2():
    """Scans all possible ports using threads (fast)."""
    threads = []
    q = Queue()

    [threads.append(Thread(target=__scan_port, args=(port, q))) for port in ls_ports()]
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]

    return {k: v for x in tuple(q.queue) for (k, v) in x.items()}


def __scan_port(port: str, q: Queue) -> dict:
    try:
        p2 = Partector2(port)
        q.put({p2._serial_number: port})
        p2.close(blocking=True)
    except Exception:
        try:
            p2.close(blocking=True)
        except UnboundLocalError:
            pass  # p2 object already destroyed
        except Exception:
            raise Exception(f"Could not close port {port}.")
