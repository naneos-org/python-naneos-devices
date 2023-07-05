import time

from naneos.partector2 import Partector2, scan_for_serial_partector2

# lists all available Partector2 devices
x = scan_for_serial_partector2()

# connect to the first device
myP2 = Partector2(list(x.values())[0], 1)
time.sleep(2)

# get the data as a pandas dataframe
data = myP2.get_data_pandas()
print(data)

myP2.close()
