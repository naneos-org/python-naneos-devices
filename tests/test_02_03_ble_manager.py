import time

import pandas as pd

from naneos.partector_ble.partector_ble_manager import PartectorBleManager


def test_ble_manager():
    manager = PartectorBleManager()
    manager.start()

    for _ in range(3):
        time.sleep(10)  # Allow some time for the scanner to start
        data = manager.get_data()

        assert isinstance(data, dict)
        assert all(isinstance(df, pd.DataFrame) for df in data.values())

    manager.stop()
