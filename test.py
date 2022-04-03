# from naneos.partector2 import Partector2
# from naneos.serial_utils import list_serial_ports
# import time

# tic = time.time()
# list_serial_ports()
# tac = time.time()
# print(f"list_serial_ports took {(tac-tic)*1e3} ms")


# tic = time.time()
# p2 = Partector2("/dev/ttyACM0")
# tac = time.time()
# print(f"Time to connect: {(tac - tic)*1e3}ms")

# print(f"Serial number: {p2._serial_number}")
# print(f"Firmware version: {p2._firmware_version}")

# time.sleep(2)

# data = p2.get_data_pandas()
# print(data)

# p2.close()
# print("Done")

# import time

# from naneos.partector2 import (
#     scan_for_serial_partector2,
#     scan_for_serial_partector2_threading,
# )

# tic = time.time()
# threding = scan_for_serial_partector2_threading()
# tac = time.time()
# print(f"scan_for_serial_partector2_threading took {(tac-tic)*1e3} ms")

# tic = time.time()
# threding = scan_for_serial_partector2()
# tac = time.time()
# print(f"scan_for_serial_partector2_threading took {(tac-tic)*1e3} ms")

# # print(scan_for_serial_partector2())

# print(threding)

# print("True" if {} else "False")
# print({**{"test": 2}, **{5: 12}})

test = {12: "asd", 7: "asasd"}

print(list(test.keys()))
