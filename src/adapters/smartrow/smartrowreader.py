import gatt
import logging
import os
import threading
from time import time, sleep

logger = logging.getLogger(__name__)

#This SDK requires you to create subclasses of gatt.DeviceManager and gatt.Device. The other two classes gatt.Service and gatt.Characteristic are not supposed to be subclassed.

#The SDK entry point is the DeviceManager class. Check the following example to dicover any Bluetooth Low Energy device nearby.


class SmartRow(gatt.Device):

    SERVICE_UUID_SMARTROW = "00001234-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_UUID_ROWWRITE = "00001235-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_UUID_ROWDATA = "00001236-0000-1000-8000-00805f9b34fb"

    def __init__(self, mac_address, manager):
        super().__init__(mac_address=mac_address, manager=manager)
        self._callbacks = set()
        self.lock = threading.Lock()
        self.is_connected = False

    def ready(self):
      with self.lock: #"Lock Acquired"
          return self.is_connected
      
    def connect_succeeded(self):
        super().connect_succeeded()
        logger.info("Connected to [{}]".format(self.mac_address))


    def connect_failed(self, error):
        super().connect_failed(error)
        logger.info("Connection failed [{}]: {} — retrying in 2s".format(self.mac_address, error))
        sleep(2)
        self.connect()

    def disconnect_succeeded(self):
        super().disconnect_succeeded()
        logger.info("Disconnected [{}]".format(self.mac_address))

    def find_service(self, uuid):
        for service in self.services:
            if service.uuid == uuid:
                return service

        return None

    def find_characteristic(self, service, uuid):
        for chrstc in service.characteristics:
            if chrstc.uuid == uuid:
                return chrstc

        return None

    def services_resolved(self):
        super().services_resolved()

        logger.info("Resolved services [{}]".format(self.mac_address))
        for service in self.services:
            logger.info("\t[{}] Service [{}]".format(self.mac_address, service.uuid))
            for characteristic in service.characteristics:
                logger.info("\t\tCharacteristic [{}]".format(characteristic.uuid))

        self.serviceSmartRow = self.find_service(self.SERVICE_UUID_SMARTROW)
        self.chrstcRowData = self.find_characteristic(self.serviceSmartRow, self.CHARACTERISTIC_UUID_ROWDATA)
        self.chrstcRowData.enable_notifications()

        self.chrstcRowWrite = self.find_characteristic(self.serviceSmartRow, self.CHARACTERISTIC_UUID_ROWWRITE)
        with self.lock: #"Lock Acquired"
            self.is_connected = True
        
    def characteristic_value_updated(self, characteristic, value):
        super().characteristic_value_updated(characteristic, value)
        try:
            decoded = value.decode('latin-1')
        except Exception as e:
            logger.warning("decode error: %s raw: %s", e, value.hex())
            return
        # SmartRow packs multiple \r-terminated messages into one notification
        for part in decoded.split('\r'):
            part = part.strip('\n')
            if part:
                self.notify_callbacks(part)


    def characteristic_write_value(self, value):
        self.writing = value
        #print(value)
        self.chrstcRowWrite.write_value(value)

    def register_callback(self, cb):
        self._callbacks.add(cb)

    def remove_callback(self, cb):
        self._callbacks.remove(cb)

    def notify_callbacks(self, event):
        for cb in self._callbacks:
            cb(event)

class SmartRowManager(gatt.DeviceManager):
    def __init__(self,*args,**kwargs):
        gatt.DeviceManager.__init__(self, *args, **kwargs)
        self.lock = threading.Lock()
        self.discovered=False 

    def ready(self):
        with self.lock:
            return self.discovered
        
    def device_discovered(self, device):
        try:
            alias = device.alias()
        except Exception as e:
            logger.info("device_discovered: alias() failed for %s (%s) — retrying", device.mac_address, e)
            # Properties not yet loaded; try again via devices() scan
            try:
                for d in self.devices():
                    if d.mac_address == device.mac_address:
                        alias = d.alias()
                        break
                else:
                    return
            except Exception:
                return
        logger.info("discovered: alias=%s mac=%s", alias, device.mac_address)
        if alias == "SmartRow":
            logging.info("found SmartRow")
            logging.info(device.mac_address)
            self.smartrowmac = device.mac_address
            with self.lock:
                self.discovered = True
            try:
                self.stop()
            except Exception:
                pass  # stop() fails if run() hasn't been called yet (device in BlueZ cache)


_MAC_CACHE_FILE = '/tmp/pirowflo_smartrow_mac'


def _save_smartrow_mac(mac):
    try:
        with open(_MAC_CACHE_FILE, 'w') as f:
            f.write(mac)
        logger.info("SmartRow MAC cached to %s", _MAC_CACHE_FILE)
    except Exception as e:
        logger.warning("could not cache SmartRow MAC: %s", e)


def _load_smartrow_mac():
    try:
        if os.path.exists(_MAC_CACHE_FILE):
            with open(_MAC_CACHE_FILE) as f:
                mac = f.read().strip()
            if mac:
                return mac
    except Exception as e:
        logger.warning("could not read SmartRow MAC cache: %s", e)
    return None


def connecttosmartrow():
    manager = SmartRowManager(adapter_name='hci0')
    logger.info("starting discovery")

    # Ensure the adapter is powered on (may be off after a crash or service restart)
    if not manager.is_adapter_powered:
        logger.info("hci0 not powered – powering on")
        manager.is_adapter_powered = True
        sleep(1)

    # Check BlueZ device cache first (fastest – no scan needed)
    for device in manager.devices():
        try:
            alias = device.alias()
        except Exception:
            alias = ""
        logger.info("known device: alias=%s mac=%s", alias, device.mac_address)
        if alias == "SmartRow":
            logger.info("SmartRow already known to BlueZ: %s", device.mac_address)
            _save_smartrow_mac(device.mac_address)
            return device.mac_address

    # Use MAC cached from a previous successful session – allows BlueZ to
    # connect directly once SmartRow wakes up, without a full scan.
    cached_mac = _load_smartrow_mac()
    if cached_mac:
        logger.info("SmartRow MAC loaded from cache (%s) – skipping scan", cached_mac)
        logger.info("Waiting for SmartRow to advertise – pull the handle to wake it up")
        return cached_mac

    # No cache: stop any stale discovery and do a fresh scan.
    # gatt silently swallows InProgress but BlueZ won't re-emit already-seen
    # devices to brand-new signal receivers, so we need a clean start.
    try:
        manager.stop_discovery()
        logger.info("stopped stale discovery on hci0")
    except Exception:
        pass  # Nothing was running – that's fine

    logger.info("starting BLE scan on hci0 – pull the SmartRow handle to wake it up")
    manager.start_discovery()
    manager.run()
    while not manager.ready():
        sleep(0.2)
    logger.info("found SmartRow macaddress: %s", manager.smartrowmac)
    _save_smartrow_mac(manager.smartrowmac)
    return manager.smartrowmac


if __name__ == '__main__':

    manager = gatt.DeviceManager(adapter_name='hci1')
    device = SmartRow(mac_address="", manager=manager)
    device.connect()

    manager.run()

    # manager = SmartRoweManager(adapter_name='hci0')
    # manager.start_discovery()
    # try:
    #     manager.run()
    # except KeyboardInterrupt:
    #     for device in manager.devices():
    #         if device.is_connected():
    #             device.disconnect()
    #     manager.stop()
