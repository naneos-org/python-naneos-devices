from queue import Queue
from threading import Thread

from naneos.partector import Partector2
from naneos.serial_utils import list_serial_ports as ls_ports


def scan_for_serial_partectors(sn_exclude: list = []) -> dict:
    """Scans all possible ports using threads (fast)."""
    threads = []
    q = Queue()

    [
        threads.append(Thread(target=__scan_port, args=(port, q)))
        for port in ls_ports()
        if port not in sn_exclude
    ]
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]

    p1 = {k: v for x in tuple(q.queue) for (k, v) in x.items() if k < 1000}
    p2 = {k: v for x in tuple(q.queue) for (k, v) in x.items() if k >= 1000}

    return {"P1": p1, "P2": p2}


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
