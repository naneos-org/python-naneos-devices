import time

from naneos.partector import Partector1, Partector2, Partector2Pro, scan_for_serial_partectors


def test_readme_example():
    PROD_NAMES = ["P1", "P2", "P2pro"]

    # Lists all available Partector devices
    partectors = scan_for_serial_partectors()
    # print eg.: {'P1': {}, 'P2': {8112: '/dev/cu.usbmodemDOSEMet_1'}, 'P2pro': {}, 'P2proCS': {}}
    print(partectors)

    for prod in PROD_NAMES:
        if len(partectors[prod]) > 0:
            for k, v in partectors[prod].items():
                print(f"Found {prod} wit serial number {k} on port {v}")
                if prod == "P1":
                    dev = Partector1(serial_number=k)
                elif prod == "P2":
                    dev = Partector2(serial_number=k)
                elif prod == "P2pro":
                    dev = Partector2Pro(serial_number=k)
                else:
                    raise ValueError(f"Unknown product name: {prod}")

                df = dev.get_data_pandas()
                max_wait_time = time.time() + 15
                while df.empty and time.time() < max_wait_time:
                    time.sleep(0.5)
                    df = dev.get_data_pandas()

                print(df)
                dev.close()


if __name__ == "__main__":
    test_readme_example()
