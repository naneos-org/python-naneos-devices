import time

from naneos.partector import Partector1, Partector2, scan_for_serial_partectors


def test_readme_example():
    # Lists all available Partector2 devices
    x = scan_for_serial_partectors()

    print(
        x
    )  # eg. {'P1': {}, 'P2': {8112: '/dev/cu.usbmodemDOSEMet_1'}, 'P2pro': {}, 'P2proCS': {}}

    # Split dictionary into P1 and P2 devices
    p1 = x["P1"]
    p2 = x["P2"]
    p2_pro = x["P2pro"]

    if len(p1) > 0:
        print("Found Partector1 devices:")
        for k, v in p1.items():
            print(f"Serial number: {k}, Port: {v}")

        # Connect to the first device with sn
        p1_dev = Partector1(serial_number=next(iter(p1.keys())))
        # or with port
        # p1_dev = Partector1(port=next(iter(p1.values())))

        time.sleep(2)

        # Get the data as a pandas DataFrame
        data = p1_dev.get_data_pandas()
        print(data)

        p1_dev.close()

    if len(p2) > 0:
        print("Found Partector2 devices:")
        for k, v in p2.items():
            print(f"Serial number: {k}, Port: {v}")

        # Connect to the first device with sn
        p2_dev = Partector2(serial_number=next(iter(p2.keys())))
        # or with port
        # p2_dev = Partector2(port=next(iter(p2.values())))

        time.sleep(2)

        # Get the data as a pandas DataFrame
        data = p2_dev.get_data_pandas()
        print(data)

        p2_dev.close()


if __name__ == "__main__":
    test_readme_example()
