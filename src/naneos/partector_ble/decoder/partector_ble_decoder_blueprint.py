from abc import ABC, abstractmethod
from typing import Optional

from naneos.partector.blueprints._data_structure import Partector2DataStructure


class PartectorBleDecoderBlueprint(ABC):
    @classmethod
    @abstractmethod
    def decode(
        cls, data: bytes, data_structure: Optional[Partector2DataStructure] = None
    ) -> Partector2DataStructure:
        """
        Decode the advertisement data from the Partector device. If the optional data_structure is
        given, it will be filled with the decoded data and returned.
        """
        pass
