import time

from naneos.partector import Partector1, Partector2, scan_for_serial_partectors

# Lists all available Partector2 devices
x = scan_for_serial_partectors()

# Split dictionary into P1 and P2 devices
p1_devs = x["P1"]
p2_devs = x["P2"]

if len(p1_devs) > 0:
    print("Found Partector1 devices:")
    for k, v in p1_devs.items():
        print(f"Serial number: {k}, Port: {v}")

    # Connect to the first device
    myP1 = Partector1(list(p1_devs.values())[0], 1)
    time.sleep(2)

    # Get the data as a pandas DataFrame
    data = myP1.get_data_pandas()
    print(data)

    myP1.close()

if len(p2_devs) > 0:
    print("Found Partector2 devices:")
    for k, v in p2_devs.items():
        print(f"Serial number: {k}, Port: {v}")

    # Connect to the first device
    myP2 = Partector2(list(p2_devs.values())[0], 1)
    time.sleep(2)

    # Get the data as a pandas DataFrame
    data = myP2.get_data_pandas()
    print(data)

    myP2.close()
