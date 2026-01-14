import cv2
import numpy as np
from enum import Enum
from returns.result import Failure, Success, Result
from returns.pipeline import is_successful


def findInGameMinimapBorder(matched_templates, minimap_border_templates, corners: list[str]) -> dict[str, (int,int)]:
    in_game_border_offsets = {}
    for corner in corners:
        matched_template = matched_templates[corner]
        template_height, template_width = minimap_border_templates[corner].shape
        center_x = matched_template.x + (template_width // 2)
        center_y = matched_template.y + (template_height // 2)
        in_game_border_offsets[corner] = (center_x, center_y)
    return in_game_border_offsets


#checks the confidence rating for each matched template loc and ensures order of matched template location is correct
def isMatchedTemplateLocValid(matched_templates: dict, corners: list[str], template_min_conf_score: float = 0.95) -> bool:
    for corner in corners:
        matched_template = matched_templates[corner]
        if matched_template.conf_score < template_min_conf_score:
            return False

    left_top, right_top, right_bot, left_bot = corners
    left_top_template, right_top_template, right_bot_template, left_bot_template = (matched_templates[left_top],
                                                                                    matched_templates[right_top],
                                                                                    matched_templates[right_bot],
                                                                                    matched_templates[left_bot])
    if left_top_template.x >= right_top_template.x or left_bot_template.x >= right_bot_template.x:
        print("Template matched locations are invalid: left-most x coord >= right-most x coord")
        return False
    if left_top_template.y >= left_bot_template.y or right_top_template.y >= right_bot_template.y:
        print("Template matched locations are invalid: top-most y coord >= right-most y coord")
        return False
    return True

##only return valid frames
def cameraGrab(camera ,minimap_detection_region_of_interest : (int, int, int, int) = None):
    frame = None
    while frame is None:
        if minimap_detection_region_of_interest is not None:
            frame = camera.grab(minimap_detection_region_of_interest)
        else:
            frame = camera.grab() #captures entire screen
    return frame

#checks if the proposed region to grab a frame is valid according to bettercamera's.grab() function, assumes screen_size is for main monitor as our comparisons are based off the coordinate space of the main monitor
def isProposedMinimapRegionValid(minimap_region: (int, int, int, int), screen_size: (int,int)) -> Result[None,str]:
    max_x_screen, max_y_screen = screen_size = screen_size[::-1] #reverse because its in (y,x) format
    x1, y1, x2, y2 = minimap_region[0], minimap_region[1], minimap_region[2], minimap_region[3]
    if x1 < 0 or y1 < 0:
        return Failure("The top-left capture region of " + str((x1,y1)) + " must be (0,0) or above.")
    if x2 > max_x_screen or y2 > max_y_screen:
        return Failure("The bottom-right capture region of " + str((x2, y2)) + " exceeds our monitor max region of " + str(screen_size))
    if x1 >= x2 or y1 >= y2:
        return Failure("The top-left capture region," + str((x1,x2)) + ", exceeds the bottom-right capture region" + str((x2,y2)))

    return Success(None)



def isMinimapBlack(minimap_frame):
    hsv_minimap_frame = cv2.cvtColor(minimap_frame, cv2.COLOR_BGR2HSV)
    black_pixel_range = np.array([0,0,0], dtype=np.uint8) #only targets black pixel range since HSV for back pixel = [0,0,0].
    normalised_mask = cv2.inRange(hsv_minimap_frame, black_pixel_range, black_pixel_range) // 255 #normalise to only 0 and 1
    (row_mask, col_mask) = normalised_mask.shape
    total_elem_in_mask = row_mask * col_mask
    total_black_pixel_in_mask = np.sum(normalised_mask)
    black_pixel_percentage_threshold = 95
    if percentOfBlackPixInMinimap(total_black_pixel_in_mask, total_elem_in_mask) >= black_pixel_percentage_threshold:
        print(percentOfBlackPixInMinimap(total_black_pixel_in_mask, total_elem_in_mask))
        return True
    return False

def percentOfBlackPixInMinimap(total_black_pixel, total_elem):
    return round(total_black_pixel / total_elem) * 100