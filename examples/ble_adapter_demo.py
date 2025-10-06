#!/usr/bin/env python3
"""
Demo script to demonstrate Bluetooth adapter checking functionality.
This script shows how the PartectorBleManager handles Bluetooth adapter availability.
"""

import asyncio
import time

from naneos.partector_ble.partector_ble_manager import PartectorBleManager


async def demo_adapter_checking():
    """Demonstrate the Bluetooth adapter checking functionality."""
    print("=== Bluetooth Adapter Checking Demo ===")
    print()

    manager = PartectorBleManager()

    # Test the adapter checking method directly
    print("Testing Bluetooth adapter availability...")
    is_available = await manager._is_bluetooth_adapter_available()
    print(f"Bluetooth adapter available: {is_available}")
    print()

    if is_available:
        print("Starting BLE Manager (it will automatically check adapter status)...")
        manager.start()

        # Let it run for a short time
        time.sleep(5)

        print(f"Connected devices: {manager.get_connected_device_strings()}")
        print("Stopping manager...")
        manager.stop()
        manager.join()
        print("Manager stopped.")
    else:
        print("Bluetooth adapter not available. Manager would wait until it becomes available.")


if __name__ == "__main__":
    asyncio.run(demo_adapter_checking())
