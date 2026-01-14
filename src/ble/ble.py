import asyncio
import threading
from bleak import BleakScanner, BleakClient
from typing import Awaitable, TypeVar
from bleak.backends.device import BLEDevice
from returns.result import Failure, Success, Result
from returns.pipeline import is_successful
import os
import janus as Janus
import subprocess




 #https://www.youtube.com/watch?v=Qb9s3UiMSTA to learn more about async in python
R = TypeVar("R") # creates a generic type named R
class BLEManager:
    _instance = None
    _instance_exist = False

    #python expects __new__ and __init__ method signature to match, but only cls is used in __new__ as only __init__ needs the
    #arguments to be able to instantiate the class attributes/methods correctly.
    def __new__(cls, ESP_32_S3_name: str):
        if cls._instance is None:
            cls._instance = super().__new__(cls) #use parent's class (object class) __new__ method to instantiate an object of type cls
            return cls._instance
        return cls._instance


    def __init__(self, ESP_32_S3_name: str):
        if BLEManager._instance_exist:
            return #prevents reinitialising of the existing singleton

        self.loop = asyncio.new_event_loop() #creates an unbounded event_loop object, get_event_loop() binds the event lop object to the thread of the calling code
        self.thread = threading.Thread(target=self._main, daemon=True) #this thread will be the thread the event loop object is bound to
        self.ble_server_device = None
        self.ble_server_address = None
        self.ble_server_service_UUID = os.getenv("KEY_INPUT_SERVICE_UUID")
        self.ble_server_characteristic_UUID = os.getenv("KEY_INPUT_CHARACTERISTIC_UUID")
        self.janus_queue_event = threading.Event() #thread-safe (managed internally) flag used to indicate when the janus.queue has been setup and is ready for inter-thread use.
        self.janus_queue : Janus.Queue[str] | None = None #will initialised later on
        self.ESP32_S3_name = ESP_32_S3_name

        BLEManager._instance_exist = True #prevents reinstantiation of our singleton

    #starts the thread that will be running the event loop object.
    def start(self):
        self.thread.start()

    #apparently this is a really scuffed way of doing it but i can't find a better way to do it.
    @classmethod
    def _is_bluetooth_enabled_windows(cls) -> Result[bool, str]:
        print("checking if bluetooth is enabled on the device")
        try:
            result = subprocess.run(['ipconfig'], #runs ipconfig.exe (same as running ipconfig in command shell but without the need for the command shell interface), saves its output as text (so it's human-readable)
                                    capture_output=True,
                                    text=True)
            return Success('Bluetooth' in result.stdout)#literally just tries to check if 'Bluetooth' is a substring inside result.stdout (which is just one giant string)
        except Exception as e:
            return Failure(str(e))

    def _main(self):
        asyncio.set_event_loop(self.loop)
        _is_bluetooth_enabled_windows_res = self.__class__._is_bluetooth_enabled_windows()
        if not is_successful(_is_bluetooth_enabled_windows_res):
            print(f"{_is_bluetooth_enabled_windows_res}.terminating BLE initialisation.")
            return
        print("Bluetooth check passed, it's enabled.")
        self.loop.run_until_complete(self._initialise_BLE_object_state_and_connect_to_ESP32_S3())


    async def _initialise_BLE_object_state_and_connect_to_ESP32_S3(self):
        print("Setting up interthread communication queue.")
        self.janus_queue = Janus.Queue() #binds the self.loop reference to the thread that runs this function
        self.janus_queue_event.set() #self.janus_queue_event.set() #sets the flag so the thread waiting on janus_queue knows that it's accessible now.
        print("interthread communication now available. janus_queue ready for use.\n")

        print("attempting to retrieve specified ESP32_S3 information")
        get_ESP32_S3_BLE_details_res = await self._get_ESP32_S3_BLE_details()
        if not is_successful(get_ESP32_S3_BLE_details_res):
            print(f"{get_ESP32_S3_BLE_details_res}. Terminating thread.")
            return
        print(f"{get_ESP32_S3_BLE_details_res}")

        print("Attempting to connect to specified ESP32_S3 device")
        await self._establish_and_maintain_connection()  #not too sure what how we want this to fully funtion yet.
        print("Attempted connection with ESP32_S3 was lost or existing connection ended. Cleaning up interthread communication resources.")
        await self.janus_queue.wait_closed()
        self.janus_queue_event.clear() # reset flag back to false

    async def _get_ESP32_S3_BLE_details(self) -> Result[str, str]:
        print("searching for ESP32_S3 BLE device. This may take some time...")
        devices = await BleakScanner.discover()
        for d in devices:
            print(d)
            if d.name == self.ESP32_S3_name:
                self.ble_server_device = d
                self.ble_server_address = d.address
                return Success(f"ESP_32_S3 ({self.ESP32_S3_name}) BLE details retrieved")
        return Failure(f"Unable to detect ESP_32_S3 named {self.ESP32_S3_name}")


    async def _establish_and_maintain_connection(self) -> None:
        ##TODO: maybe implement this? Honestly I don't really know what i need to do for this
        def on_abrupt_disconnect(bleak_client):
            print("An unexpected disconnection to the ESP32-S3 occurred.")

        ##TODO: (only do this after going through the todo.txt in the ble folder)fully implement this method, right now it just takes and prints it out to console, no communication to the BLE device happens
        #create as a task,
        async def _read_send_data_in_janus_queue():
            while client.is_connected:
                    item = await self.janus_queue.async_q.get() #Yields until queue signals event loop that item is available
                    print("----------------------------------------------------")
                    print(f"data received from janus queue {item}")
                    item_utf8 = item.encode("utf-8")# encode whatever we get into its corresponding UTF-8 representation which will be a byte array where each value maps to a corresponding byte. UTF-8 is a superset of ASCII but is backwards compatible with ASCII as the first 128 characters are represented with the same bytes
                    print("Writing data to characteristic in ESP32-S3")
                    await client.write_gatt_char(self.ble_server_characteristic_UUID, item_utf8)
                    print("Data written to characteristic in ESP32-S3")
                    print("----------------------------------------------------")

        if not self.ble_server_device or not self.ble_server_address:
            print("BLE address is None. BLEManager did not find the ESP32-S3 device")
            return

        #actual code begins below here

        client = BleakClient(self.ble_server_address, disconnected_callback=on_abrupt_disconnect) #need to add in disconnect callback too but i'm not really too sure how that works yet so leaving for now

        try:
            await client.connect()
        except Exception as e:
            print(f"Error encountered when establishing connection with {self.ESP32_S3_name}: {e}. Ending connection attempt.")
            return

        print(f"BLE connection with {self.ESP32_S3_name} established")

        asyncio.create_task(_read_send_data_in_janus_queue()) #create task for reading and sending data from janus queue

        while client.is_connected:
            await asyncio.sleep(30) #minimise time spent in this async function, maximise time spent in the _read_send_data_in_janus_queue() task

        print(f"client connection with {self.ESP32_S3_name} was disconnected")
        await self.janus_queue.wait_closed()
        self.janus_queue_event.set()
        return



















