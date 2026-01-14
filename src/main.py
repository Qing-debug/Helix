import threading
from src.vision.vision_v2 import MinimapScanner
from src.gui.gui import MapleGUI
from src.controller.controller import Controller
from pathlib import Path
import os
from dotenv import load_dotenv
from src.classes.classes import * #imports maple classes

load_dotenv() #loads env variables into environment (accessible through the entire process)

class SharedInfo:
    def __init__(self):
        self.minimap_frame_lock = threading.Lock()
        self.minimap_frame = None #note: numpy array storing data in BGR format.

def main():
    CSV_path = os.getenv("MAP_PATH")
    CSV = Path(CSV_path)
    sharedInfo = SharedInfo()

    ESP32_S3_name = "guiness"  # to be given into the BLE manager object upon instantiation

    WINDOWS_MAIN_MONITOR = 0
    TIMEOUT_TIME = 30
    minimapScanner = MinimapScanner(sharedInfo=sharedInfo, project_root=Path(__file__).parent.parent,
                                    output_screen_to_capture=WINDOWS_MAIN_MONITOR)
    minimapScanner.start()
    if not minimapScanner.minimap_frame_ready_event.wait(timeout=TIMEOUT_TIME):
        print(f"minimapScanner timed out after waiting {TIMEOUT_TIME} seconds. Aborting Program.")
        return
    controller = Controller(sharedInfo=sharedInfo, CSV=CSV, characterClass=None)
    gui = MapleGUI(controller=controller, sharedInfo=sharedInfo)
    gui.start()  # this starts another thread for


if __name__ == "__main__":
    main()