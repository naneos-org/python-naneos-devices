from naneos.data_point import DeviceType
from naneos.partector.blueprints._data_structure import PARTECTOR1_DATA_STRUCTURE_V_LEGACY
from naneos.partector.blueprints._partector_blueprint import PartectorBlueprint


class Partector1(PartectorBlueprint):
    DEVICE_TYPE = DeviceType.P1

    def _configure(self) -> None:
        self._data_structure = dict(PARTECTOR1_DATA_STRUCTURE_V_LEGACY)
        self._legacy_data_structure = True
