import time

from naneos.partector import Partector2ProGarage

if __name__ == "__main__":
    p2 = Partector2ProGarage("/dev/tty.usbmodemDOSEMet_1")

    print(p2.write_line("v?", 1))
    time.sleep(2)
    print(p2.get_data_pandas()["T"])
    p2.close()
