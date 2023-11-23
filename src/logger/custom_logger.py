import logging


class CustomFormatter(logging.Formatter):
    grey = "\x1b[38;20m"
    green = "\x1b[32;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = (
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    )

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: green + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def get_naneos_logger(name: str):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    formatter_file = logging.Formatter("%(asctime)s - %(filename)s - %(message)s")
    file_handler = logging.FileHandler("naneos-devices.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter_file)

    formatter_stream = CustomFormatter("%(asctime)s - %(filename)s - %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter_stream)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)

    return logger


# def get_naneos_logger(log_file_name):
#     # Erstellt einen Logger
#     logger = logging.getLogger(__name__)
#     logger.setLevel(logging.DEBUG)

#     # Erstellt einen Formatter, der das Datum, den Dateinamen und die Nachricht enthält
#     formatter = logging.Formatter("%(asctime)s - %(filename)s - %(message)s")

#     # Erstellt einen FileHandler, um das Protokoll in eine Datei zu schreiben
#     file_handler = logging.FileHandler("naneos-devices.log")
#     file_handler.setLevel(logging.DEBUG)
#     file_handler.setFormatter(formatter)

#     # Erstellt einen StreamHandler, um das Protokoll auf der Konsole auszugeben
#     stream_handler = logging.StreamHandler()
#     stream_handler.setLevel(logging.DEBUG)
#     stream_handler.setFormatter(CustomFormatter)

#     # Fügt die Handler dem Logger hinzu
#     logger.addHandler(file_handler)
#     logger.addHandler(stream_handler)

#     return logger
