import asyncio
import base64
import datetime
from queue import Queue
from threading import Event, Thread
import time

import requests

from naneos.partector import Partector1, scan_for_serial_partectors
from naneos.protobuf import create_combined_entry, create_partector1_entry


class P1uploadThread(Thread):
    def __init__(self) -> None:
        Thread.__init__(self)
        self.event = Event()
        self.event.set()
        self.connect_queue = Queue()
        self.disconnect_queue = Queue()

        self.device_list = []
        self.last_send_time = time.time()  # change to asyncio loop
        self.start()

    def run(self) -> None:
        asyncio.run(self.run_async())

        print("closing devices")
        for d in self.device_list:
            d.close()

    async def run_async(self) -> None:
        task1 = asyncio.create_task(self.connect_disconnect_routine())
        task2 = asyncio.create_task(self._send_data_to_server())

        await task1
        await task2

    async def connect_disconnect_routine(self):
        while self.event.is_set():
            self._connect_to_ports_from_queue()
            self._disconnect_from_void_ports()
            self._disconnect_from_ports_from_queue()

            await asyncio.sleep(0.1)

    def get_connected_devices_ports(self):
        return [d._ser.port for d in self.device_list]

    def _connect_to_ports_from_queue(self):
        connected_ports = self.get_connected_devices_ports()

        while not self.connect_queue.empty():
            port = self.connect_queue.get()
            if port not in connected_ports:
                print(f"Connecting to {port}")
                self.device_list.append(Partector1(port))

    def _disconnect_from_void_ports(self):
        for d in self.device_list:
            # print(d.last_heard)
            if d.last_heard < time.time() - 10:
                print(f"Disconnecting from {d._ser.port}")
                d.close()
                self.device_list.remove(d)

    def _disconnect_from_ports_from_queue(self):
        connected_ports = self.get_connected_devices_ports()

        while not self.disconnect_queue.empty():
            port = self.disconnect_queue.get()
            if port in connected_ports:
                # close the device in list and remove it from the list
                for d in self.device_list:
                    if d._ser.port == port:
                        d.close()
                        self.device_list.remove(d)

    async def _send_data_to_server(self):
        while self.event.is_set():
            # print("Sending data to server")
            await asyncio.sleep(15)

            if len(self.device_list) == 0:
                continue

            abs_time = int(datetime.datetime.now().timestamp())
            devices = []
            for d in self.device_list:
                df = d.get_data_pandas()
                devices.append(create_partector1_entry(df, d._serial_number, abs_time))

            combined = create_combined_entry(devices=devices, abs_timestamp=abs_time)

            proto_string = combined.SerializeToString()
            proto_string_base64 = base64.b64encode(proto_string)
            # print(proto_string_base64)

            # send this string to the server
            url = "https://hg3zkburji.execute-api.eu-central-1.amazonaws.com/prod/proto/v1"
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            body = f"""
                    {{
                        "gateway": "python_webhook",
                        "data": "{proto_string_base64.decode()}",
                        "published_at": "{datetime.datetime.now().isoformat()}"
                    }}
                    """

            # print(body)

            # send the data to the server
            r = requests.post(url, headers=headers, data=body)
            print(f"Status code: {r.status_code}, text: {r.text}")


if __name__ == "__main__":
    upload_thread = P1uploadThread()
    time.sleep(1)

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
