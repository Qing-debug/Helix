import asyncio
import threading

from bleak import BleakScanner

 #https://www.youtube.com/watch?v=Qb9s3UiMSTA to learn more about async in python

async def find_available_BLE_mac_address():
    devices = await BleakScanner.discover()
    for d in devices:
        print(d)

async def establish_connection():



class BLEManager:
    def __init__(self):
        self.loop = asyncio.new_event_loop() #creates an unbounded event_loop object, get_event_loop() binds the event lop object to the thread of the calling code
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True) #this thread will be the thread the event loop object is bound to
        

    #starts the thread that will be running the event loop object.
    def start(self):
        self.thread.start()

    #run this first to get the appropriate MAC address of your BLE device. Establish connection later using that MAC address in your main.

    #expects an async function to pass to the event loop.
    def pass_coroutine_to_event_loop_and_block_till_future_resolves(self, coroutine):
         future = asyncio.run_coroutine_threadsafe(coroutine, self.loop) #returns a Concurrent.Future.future object (threadsafe), not asyncio.future (not threadsafe). run_coroutine_threadsafe() acts as a bridge as it allows async code to be called from a synchronous context (and implicitly across threads since asnc code and sync code cannot be in the same thread), and we can mimic the functionality of await in that synchronous context through the use of .result()
         result = future.result() #.result() is a blocking operation that only unblocks the thread calling this function once the future returned by the event loop running in the background thread has a value.
         return result







