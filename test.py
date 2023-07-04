import time

from naneos.partector2 import Partector2, scan_for_serial_partector2

x = scan_for_serial_partector2()

myP2 = Partector2(list(x.values())[0], 1)

time.sleep(2)

data = myP2.get_data_pandas()

print(data)


myP2.close()
