from abc import ABC, abstractmethod
from typing import Optional

from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint


class PartectorBleDecoderBlueprint(ABC):
    @classmethod
    @abstractmethod
    def decode(
        cls, data: bytes, data_structure: Optional[NaneosDeviceDataPoint] = None
    ) -> NaneosDeviceDataPoint:
        """
        Decode the advertisement data from the Partector device. If the optional data_structure is
        given, it will be filled with the decoded data and returned.
        """
        pass
