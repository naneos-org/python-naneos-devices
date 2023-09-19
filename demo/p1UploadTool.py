import time

from naneos.iotweb import P1uploadThread
from naneos.partector import scan_for_serial_partectors


def main():
    upload_thread = P1uploadThread()
    time.sleep(0.2)

    # wait for keyboard interrupt
    try:
        while True:
            time.sleep(1)
            connected_ports = upload_thread.get_connected_devices_ports()
            devs = scan_for_serial_partectors(sn_exclude=connected_ports)["P1"]
            # print(devs)

            # add all devices to the queue
            for v in devs.values():
                print(f"Adding {v} to queue")
                upload_thread.connect_queue.put(v)
    except KeyboardInterrupt:
        pass

    # stop the thread
    upload_thread.event.clear()
    upload_thread.join()


if __name__ == "__main__":
    main()
