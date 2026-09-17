# Logging
The package follows the usual library convention: it logs to loggers below `naneos` and prints
nothing unless the application configures logging. To see what the managers are doing:
```python
from naneos.logger import LEVEL_INFO, enable_console_logging, enable_file_logging

enable_console_logging(LEVEL_INFO)  # coloured output on stderr
enable_file_logging("logs/", LEVEL_INFO)  # appends to logs/naneos-devices.log
```
Applications that configure `logging` themselves need neither; the `naneos` logger propagates
to the root logger like any other library.

