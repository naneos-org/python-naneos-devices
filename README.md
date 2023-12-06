# naneos (python-toolkit)

[![GitHub Actions][github-actions-badge]](https://github.com/naneos-org/python-naneos-devices/actions)
[![GitHub Issues][gh-issues]](https://github.com/naneos-org/python-naneos-devices/issues)
[![GitHub Pull Requests][gh-pull-requests]](https://github.com/naneos-org/python-naneos-devices/pulls)
[![Poetry][poetry-badge]](https://python-poetry.org/)
[![Nox][nox-badge]](https://github.com/wntrblm/nox)
[![Code style: Black][black-badge]](https://github.com/psf/black)
[![Ruff][ruff-badge]](https://github.com/astral-sh/ruff)
[![Type checked with mypy][mypy-badge]](https://mypy-lang.org/)
[![License][mit-license]](LICENSE.txt)

<!-- hyperlinks -->
[github-actions-badge]: https://github.com/naneos-org/python-naneos-devices/actions/workflows/pages.yml/badge.svg
[poetry-badge]: https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json
[nox-badge]: https://img.shields.io/badge/%F0%9F%A6%8A-Nox-D85E00.svg
[black-badge]: https://img.shields.io/badge/code%20style-black-000000.svg
[ruff-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
[mypy-badge]: https://www.mypy-lang.org/static/mypy_badge.svg
[mit-license]: https://img.shields.io/badge/license-MIT-blue.svg
[gh-issues]: https://img.shields.io/github/issues/naneos-org/python-naneos-devices/issues
[gh-pull-requests]: https://img.shields.io/github/issues-pr/naneos-org/python-naneos-devices
<!-- hyperlinks -->

[![Naneos Logo](https://raw.githubusercontent.com/naneos-org/python-naneos-devices/ce12c8b613211c92ac15c9a1c20a53433268c91b/naneos_logo.svg)](https://naneos.ch)

This repository contains a collection of Python scripts and utilities for our [naneos](https://naneos.ch) measurement devices. These scripts will provide various functionalities related to data acquisition, analysis, and visualization for your measurement devices.

# Installation

You can install the `naneos-devices` package using pip. Make sure you have Python 3.9 or higher installed. Open a terminal and run the following command:

```bash
pip install naneos-devices
```

# Usage

To establish a serial connection with the Partector2 device and retrieve data, you can use the following code snippet as a starting point:

```python
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

```

Make sure to modify the code according to your specific requirements. Refer to the documentation and comments within the code for detailed explanations and usage instructions.

# Documentation

The documentation for the `naneos-devices` package can be found in the [package's documentation page](https://naneos-org.github.io/python-naneos-devices/).

<!-- ## Important commands when working locally with tox
```bash
tox -e clean #cleans the dist and docs/_build folder
tox -e build #builds the package based on the last tag
pipenv install -e . #installs the locally builded package

tox -e docs #generates the documentation
$
tox -e publish  # to test your project uploads correctly in test.pypi.org
tox -e publish -- --repository pypi  # to release your package to PyPI

tox -av  # to list all the tasks available

### Testing with tox
# 1. Install the desired version with pyenv
pyenv install 3.8.X 3.9.X, 3.10.X, 3.11.X, 3.12.X
# 2. Set the desired versions global
pyenv global 3.8.X 3.9.X 3.10.X 3.11.X 3.12.X
# 3. Run tox
tox
```
It's recommended to use a .pypirc file to store your credentials. See [here](https://packaging.python.org/en/latest/specifications/pypirc/) for more information. -->

# Protobuf
Use this command to create a py and pyi file from the proto file
```bash
protoc -I=. --python_out=. --pyi_out=. ./protoV1.proto 
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
