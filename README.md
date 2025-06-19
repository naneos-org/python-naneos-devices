# naneos-devices


[![GitHub Issues][gh-issues]](https://github.com/naneos-org/python-naneos-devices/issues)
[![GitHub Pull Requests][gh-pull-requests]](https://github.com/naneos-org/python-naneos-devices/pulls)
[![Ruff][ruff-badge]](https://github.com/astral-sh/ruff)
[![License][mit-license]](LICENSE.txt)

<!-- hyperlinks -->
[gh-issues]: https://img.shields.io/github/issues/naneos-org/python-naneos-devices
[gh-pull-requests]: https://img.shields.io/github/issues-pr/naneos-org/python-naneos-devices
[ruff-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
[mit-license]: https://img.shields.io/badge/license-MIT-blue.svg
<!-- hyperlinks -->

[![Projektlogo](https://raw.githubusercontent.com/naneos-org/public-data/master/img/logo_naneos.png)](https://naneos.ch)

This repository contains a collection of Python scripts and utilities for our [naneos particle solutions](https://naneos.ch) measurement devices. These scripts will provide various functionalities related to data acquisition, analysis, and visualization for your measurement devices.

# Installation

You can install the `naneos-devices` package using pip. Make sure you have Python 3.10 or higher installed. Open a terminal and run the following command:

```bash
pip install naneos-devices
```

# Usage

To establish a serial connection with the Partector2 device and retrieve data, you can use the following code snippet as a starting point:

```python
import time

from naneos.partector import PartectorSerialManager


manager = PartectorSerialManager()
manager.start()

time.sleep(15)  # Let the manager run for a while
data = manager.get_data()

manager.stop()
manager.join()

print("Collected data:")
print()
for sn, df in data.items():
    print(f"SN: {sn}")
    print(df)
    print("-" * 40)
    print()
```

Make sure to modify the code according to your specific requirements. Refer to the documentation and comments within the code for detailed explanations and usage instructions.

# Documentation

The documentation for the `naneos-devices` package can be found in the [package's documentation page](https://naneos-org.github.io/python-naneos-devices/).

# Protobuf
Use this command to create a py and pyi file from the proto file
```bash
protoc -I=. --python_out=. --pyi_out=. ./protoV1.proto 
```

# Testing
I recommend working with uv.
Testing with the local python venv in vscode GUI or with:
```bash
uv run --env-file .env pytest
```

Testing every supported python version:
```bash
nox -s tests
```

# Building executables
Sometimes you want to build an executable for a customer with you custom script.
The build must happen on the same OS as the target OS.
For example if you want to build an executable for windows you need to build it on Windows.

```bash
pyinstaller demo/p1UploadTool.py  --console --noconfirm --clean --onefile
```

# Ideas for future development
* P2 BLE implementation that integrates into the implementation of the serial P2
* P2 Bidirectional Implementation that allows to send commands to the P2
* Automatically activate Bluetooth or ask when BLE is used

# Contributing

Contributions are welcome! If you encounter any issues or have suggestions for improvements, please submit an issue on the [issue tracker](https://github.com/naneos-org/python-naneos-devices/issues).

Please make sure to adhere to the coding style and conventions used in the repository and provide appropriate tests and documentation for your changes.

# License

This repository is licensed under the [MIT License](LICENSE.txt).

# Contact

For any questions, suggestions, or collaborations, please feel free to contact the project maintainer:

- Mario Huegi
- Contact: [mario.huegi@naneos.ch](mailto:mario.huegi@naneos.ch)
- [Github](https://github.com/huegi)
