import time

from naneos.partector import PartectorSerialManager


def test_readme_example():
    manager = PartectorSerialManager()
    manager.start()

    time.sleep(15)  # Let the manager run for a while
    data = manager.get_data()

    manager.stop()
    manager.join()

    assert isinstance(data, dict), "Data should be a dictionary."
    assert len(data) > 0, "Data dictionary should not be empty."

    print("Collected data:")
    print()
    for sn, df in data.items():
        print(f"SN: {sn}")
        print(df)
        print("-" * 40)
        print()


if __name__ == "__main__":
    test_readme_example()
