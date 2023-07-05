# naneos-devices (python toolkit)

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE.txt)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11-blue)](https://www.python.org/)
[![GitHub Issues](https://img.shields.io/github/issues/naneos-org/python-naneos-devices/issues)](https://github.com/naneos-org/python-naneos-devices/issues)
[![GitHub Pull Requests](https://img.shields.io/github/issues-pr/naneos-org/python-naneos-devices)](https://github.com/naneos-org/python-naneos-devices/pulls)

[![Naneos Logo](naneos_logo.svg)](https://naneos.ch)


This repository contains a collection of Python scripts and utilities for our naneos measurement devices. These scripts will provide various functionalities related to data acquisition, analysis, and visualization for your measurement devices.

## Installation

You can install the `naneos-devices` package using pip. Make sure you have Python 3.9 or higher installed. Open a terminal and run the following command:

```bash
pip install naneos-devices
```

## Usage

To establish a serial connection with the Partector2 device and retrieve data, you can use the following code snippet as a starting point:

```python
import time
from naneos.partector2 import Partector2, scan_for_serial_partector2

# Lists all available Partector2 devices
x = scan_for_serial_partector2()

# Connect to the first device
myP2 = Partector2(list(x.values())[0], 1)
time.sleep(2)

# Get the data as a pandas DataFrame
data = myP2.get_data_pandas()
print(data)

myP2.close()
```

Make sure to modify the code according to your specific requirements. Refer to the documentation and comments within the code for detailed explanations and usage instructions.

## Documentation

The documentation for the `naneos-devices` package can be found in the [package's documentation folder](docs/index.md).

## Contributing

Contributions are welcome! If you encounter any issues or have suggestions for improvements, please submit an issue on the [issue tracker](https://github.com/naneos-org/python-naneos-devices/issues). If you'd like to contribute code, please follow the guidelines mentioned in the [CONTRIBUTING](CONTRIBUTING.rst) file.

Please make sure to adhere to the coding style and conventions used in the repository and provide appropriate tests and documentation for your changes.

## License

This repository is licensed under the [MIT License](LICENSE.txt).

## Acknowledgments

If you would like to acknowledge any individuals, organizations, or resources that have been helpful to your project, you can include them in this section.

## Contact

For any questions, suggestions, or collaborations, please feel free to contact the project maintainer:

- Mario Huegi
- Contact: [mario.huegi@naneos.ch](mailto:mario.huegi@naneos.ch)
- [Github](https://github.com/huegi)