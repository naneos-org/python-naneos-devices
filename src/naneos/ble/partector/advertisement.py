from bleak.backends.scanner import AdvertisementData


class PartectorBleDecoder:
    """
    Decode the BLE advertisement of a Partector.
    """

    # One frame: protocol byte, 20 payload bytes, protocol byte.
    FRAME_LENGTH = 22
    PROTOCOL_BYTE_START = b"X"[0]  # the advertisement, the payload of the std characteristic
    PROTOCOL_BYTE_END = b"F"[0]
    # The scan response ("Y") carries the aux data. The scanner only needs the
    # serial number, which the advertisement holds, so it is not decoded.

    SLICE_PAYLOAD = slice(1, 21)

    # == Public Methods ============================================================================
    @classmethod
    def decode_partector_advertisement(cls, adv: AdvertisementData) -> bytes | None:
        """
        The 20 payload bytes of the newest advertisement frame of the device (the same
        bytes as the std characteristic), or None if there is none.

        We are violating the BLE standard here by using the manufacturer data field for our
        own purposes. Not good practice, but the only way to put more data into the advertisement.

        Because the two protocol bytes end up in the manufacturer id, almost every
        frame arrives under a different id. BlueZ merges those into one map and
        never evicts an entry, so manufacturer_data holds every frame seen from
        the device, not the current one. Picking the first entry therefore froze
        the reading at the oldest frame, and returned nothing at all whenever that
        frame happened to be a scan response.

        Frames are selected by their protocol byte instead, keeping the last one.
        Insertion order is the only ordering the map offers, so "last" is a best
        effort - an id that repeats keeps its original position while its payload
        is updated in place.
        """
        newest: bytes | None = None

        for manufacturer_id, payload in adv.manufacturer_data.items():
            frame = manufacturer_id.to_bytes(2, "little") + payload

            # Backends that hand over advertisement and scan response already
            # concatenated are split here, so both halves take the same path.
            if len(frame) == 2 * cls.FRAME_LENGTH:
                frames = [frame[: cls.FRAME_LENGTH], frame[cls.FRAME_LENGTH :]]
            else:
                frames = [frame]

            for candidate in frames:
                if (
                    len(candidate) == cls.FRAME_LENGTH
                    and candidate[0] == cls.PROTOCOL_BYTE_START
                    and candidate[-1] == cls.PROTOCOL_BYTE_END
                ):
                    newest = candidate

        return None if newest is None else newest[cls.SLICE_PAYLOAD]
