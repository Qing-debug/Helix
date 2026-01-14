import bettercam
import cv2
from pathlib import Path
import src.vision.vision_helper_lib as vision_helper
import time
from collections import namedtuple
import datetime
import threading
from returns.result import Failure, Success, Result
from returns.pipeline import is_successful

class MinimapScanner:
    #used for singleton pattern
    _instance = None
    _instance_exist = False

    #Static Constants used to configure minimap capture process
    MINIMAP_POSITION_RECALC_INTERVAL = 1000
    FRAME_DELAY_MS = 10  # main determinant in while loop execution speed
    THREAD_SLEEP_DURATION_S = 0.01
    FOREGROUND_CHECK_SLEEP_S = 5
    MINIMAP_DETECTION_RETRY_DELAY_S = 1
    WINDOW_HANDLE_RETRY_DELAY_S = 3
    MINIMAP_TEMPLATE_MATCH_CONFIDENCE_THRESHOLD = 0.95

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls) #
            return cls._instance
        return cls._instance

    def __init__(self, sharedInfo, project_root, output_screen_to_capture):
        if self.__class__._instance_exist:
            return
        #shared object for inter-thread communication between GUI and this thread.
        self.sharedInfo = sharedInfo

        #used for setup
        self.project_root = project_root
        self.output_idx = output_screen_to_capture
        self.corners = ["left_top", "right_top", "right_bot", "left_bot"]

        #will be initialised using a setup() method
        self.minimap_paths = None
        self.camera = None
        self.minimap_border_templates = {}
        self.minimap_border_masks = {}

        #threading stuff
        self.thread = threading.Thread(target = self._main, daemon=True)
        self.minimap_frame_ready_event = threading.Event() #Used so we know if we can continue with program execution or not

        self.__class__._instance_exist = True

    def start(self):
        self.thread.start()

    def _main(self) -> Result[None, str]:
        setup_res = self._setup()
        print(setup_res)
        if not is_successful(setup_res):
            print(f"minimap capture thread failed to start properly.")
            return #early return
        self._capture_and_process_minimap() #runs indefinitely


    def _setup(self) -> Result[None, str] :
        print("-------Setting Up MinimapScanner Singleton...-------")

        print("setting up file paths to minimap border and mask images...")
        self.minimap_paths = {corner: {
            "border": self.project_root / "assets" / "brds" / f"{corner}_grayscale.png",
            "mask": self.project_root / "assets" / "brds" / f"{corner}_mask.png"
        } for corner in self.corners}
        print("minimap border and mask images setup - Done \n ")

        print("setting up bettercam camera...")
        self.camera = bettercam.create(output_idx=self.output_idx, output_color="BGR")
        print(f"target monitor for screen grab is currently monitor {self.output_idx}. main monitor = 0.")
        print("bettercam camera setup - Done\n")

        print("Setting up in-memory representation of minimap border templates and masks...")
        for corner in self.corners:
            self.minimap_border_templates[corner] = cv2.imread(str(self.minimap_paths[corner]["border"]), cv2.IMREAD_GRAYSCALE)
            self.minimap_border_masks[corner] = cv2.imread(str(self.minimap_paths[corner]["mask"]), cv2.IMREAD_GRAYSCALE)
        print("minimap border templates and masks setup - Done\n")

        print("Final Check - ensure these are correct")
        print(f"minimap file path: {self.minimap_paths}")
        print(f"camera:{self.camera}")
        print(f"minimap border templates:{self.minimap_border_templates}")
        print(f"minimap border masks:{self.minimap_border_masks}\n")

        if self.minimap_paths is None or self.camera is None or self.minimap_border_templates == {} or self.minimap_border_masks == {}:
            return Failure("MinimapScanner Setup Failed.")

        print("-------MinimapScanner Singleton Setup Complete-------")
        return Success("MinimapScanner Successfully Setup ")


    def _capture_and_process_minimap(self):
        MatchedTemplateInfo = namedtuple("MatchedTemplateInfo", ["x", "y", "conf_score"])

        print("beginning minimap capture process...")
        while True:
            entire_monitor_frame = vision_helper.cameraGrab(self.camera)
            screen_size = entire_monitor_frame.shape[:2]
            minimap_gray = cv2.cvtColor(entire_monitor_frame, cv2.COLOR_BGR2GRAY)

            # try to find minimap from frame of entire monitor
            matched_template_loc_and_conf_score = {}
            for corner in self.corners:
                matched_loc = cv2.matchTemplate(minimap_gray, self.minimap_border_templates[corner], cv2.TM_CCORR_NORMED,
                                                mask=self.minimap_border_masks[corner])
                _, max_val, _, max_loc = cv2.minMaxLoc(matched_loc)
                x, y = max_loc
                matched_template_loc_and_conf_score[corner] = MatchedTemplateInfo(x=x, y=y, conf_score=max_val)

            # retry from beginning if computed template location for minimap borders is not valid (could be due to invalid minimap image)
            if not vision_helper.isMatchedTemplateLocValid(matched_template_loc_and_conf_score, self.corners,
                                                    self.__class__.MINIMAP_TEMPLATE_MATCH_CONFIDENCE_THRESHOLD):
                print(
                    "Minimap border template matching failed or returned invalid results. Retrying minimap detection...")
                continue

            minimap_border_locations = vision_helper.findInGameMinimapBorder(matched_template_loc_and_conf_score,
                                                                      self.minimap_border_templates, self.corners)
            top_left, bottom_right = minimap_border_locations["left_top"], minimap_border_locations["right_bot"]
            minimap_region, minimap_valid, minimap_frame_counter = (*top_left, *bottom_right), True, 0
            while minimap_valid and minimap_frame_counter < self.__class__.MINIMAP_POSITION_RECALC_INTERVAL:
                isProposedCaptureRegionValid = vision_helper.isProposedMinimapRegionValid(minimap_region, screen_size)
                if not is_successful(isProposedCaptureRegionValid):
                    print(f"The proposed capture region is invalid. Here is the exact issue: {isProposedCaptureRegionValid}")
                    break
                minimap_frame = vision_helper.cameraGrab(self.camera, minimap_region)

                if vision_helper.isMinimapBlack(minimap_frame):
                    print("Minimap frame is detected to be black. Retrying minimap detection...")
                    minimap_valid = False
                    time.sleep(self.__class__.MINIMAP_DETECTION_RETRY_DELAY_S)
                    break
                with self.sharedInfo.minimap_frame_lock:
                    self.sharedInfo.minimap_frame = cv2.cvtColor(minimap_frame, cv2.COLOR_BGR2RGB)
                    if not self.minimap_frame_ready_event.is_set():
                        self.minimap_frame_ready_event.set()
                        print("First minimap frame successfully captured. Setting flag to true so GUI can begin execution.")
                minimap_frame_counter += 1
                cv2.imshow("Minimap", minimap_frame)
                # print(f"{datetime.datetime.now()}")
                cv2.waitKey(
                    self.__class__.FRAME_DELAY_MS)  # for some reason, longer delay time == lower occurrence of camera.grab() returning none regardless of the content
                time.sleep(self.__class__.THREAD_SLEEP_DURATION_S)  # give time for other threads (like the pathfinding thread) to run.













