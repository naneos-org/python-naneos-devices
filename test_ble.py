import time

from naneos.partector2_ble import Partector2Ble

myP2 = Partector2Ble()

time.sleep(10)

x = myP2.get_and_clear_results()

print(x)

myP2.stop_scanning()
