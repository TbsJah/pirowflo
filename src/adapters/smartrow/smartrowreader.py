import gatt
import logging
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
        except Exception:
            return  # device properties not yet available, ignore
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


def connecttosmartrow():
    manager = SmartRowManager(adapter_name='hci0')
    logger.info("starting discovery")

    # Device may already be known from BlueZ cache (found during __init__)
    if manager.ready():
        logger.info("SmartRow found in BlueZ cache: %s", manager.smartrowmac)
        return manager.smartrowmac

    # Also check device list directly
    for device in manager.devices():
        if device.alias() == "SmartRow":
            logger.info("SmartRow already known: %s", device.mac_address)
            return device.mac_address

    manager.start_discovery()
    manager.run()
    while not manager.ready():
        time.sleep(0.2)
    logger.info("found SmartRow macaddress")
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
