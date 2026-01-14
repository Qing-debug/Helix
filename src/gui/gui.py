import tkinter as tk
from PIL import Image, ImageTk
import networkx as nx
import matplotlib.pyplot as plt
import time
from returns.pipeline import is_successful
from src.controller.node import  CharacterNode


class MapleGUI:
    def __init__(self, controller = None, sharedInfo = None ):
        self.minimap_canvas_width = None
        self.minimap_canvas_height = None
        self.minimap_canvas = None
        self.minimap_canvas_bg_img_id = None #new
        self.gui = tk.Tk()
        self.gui_console = tk.Text(self.gui)
        self.node_count = 0
        self.controller = controller
        self.sharedInfo = sharedInfo

    def start(self):
        print("Starting GUI...")
        self._setupGUI()
        self._updateCanvas()
        self.gui.mainloop()

    def _setupGUI(self):
        self.gui.configure(bg='lightblue')
        self.gui.geometry("1000x1000")
        self.gui_console.pack()

        draw_blue_node_button = tk.Button(self.gui, text="draw blue node on character", command=self.drawBlueNodeOnCharacter)
        draw_blue_node_button.pack(side=tk.TOP, pady=5)

        draw_orange_node_button = tk.Button(self.gui, text="draw orange node on character", command=self.drawOrangeNodeOnCharacter)
        draw_orange_node_button.pack(side=tk.TOP, pady=5)

        clear_gui_console_button = tk.Button(self.gui, text = "clear console", command = self.clearGUIConsole)
        clear_gui_console_button.pack(side=tk.TOP, pady=5)

        clear_gui_minimap_button = tk.Button(self.gui, text = "clear drawn nodes on minimap", command = self._clearDrawnNodesOnGUIMinimap)
        clear_gui_minimap_button.pack(side=tk.TOP, pady=5)

        #delete once we have no need for direct testing or move to a separate part of GUI for testing purposes only
        # parse_CSV_button = tk.Button(self.gui, text = "(delete or move to a separate tab on the GUI) parse CSV", command = self.controller.parseCSV)
        # parse_CSV_button.pack(side=tk.TOP, pady=5)

        #delete once we have no need for direct testing or move to a separate part of GUI for testing purposes only
        # build_graph_button = tk.Button(self.gui, text = "(delete or move to a separate tab on the GUI) create edges", command = self.controller.buildGraph)
        # build_graph_button.pack(side=tk.TOP, pady=5)

        setup_bot_button = tk.Button(self.gui, text = "(delete or move to a separate tab on the GUI) setup bot", command = self.mockSetupBotEnvironment)
        setup_bot_button.pack(side = tk.TOP, pady=5)

        #delete once we have no need for direct testing or move to a separate part of GUI for testing purposes only
        display_graph_button = tk.Button(self.gui, text="(delete or move to a separate tab on the GUI) used to visualise the graph", command=self._drawGraph)
        display_graph_button.pack(side=tk.TOP, pady=5)

        #delete once we have no need for direct testing or move to a separate part of GUI for testing purposes only
        connect_character_node_button = tk.Button(self.gui, text="(delete or move to a separate tab on the GUI) used to add character node to graph (node is d in just for testing purposes only)", command=self.controller.connectCharacterNode)
        connect_character_node_button.pack(side=tk.TOP, pady=5)
        #
        #delete once we have no need for direct testing or move to a separate part of GUI for testing purposes only
        delete_node_button = tk.Button(self.gui, text="(delete or move to a separate tab on the GUI) used to delete character node from graph (node is hardcoded in just for testing purposes only)", command=self.controller.deleteNode)
        delete_node_button.pack(side=tk.TOP, pady=5)

        # delete once we have no need for direct testing
        get_path = tk.Button(self.gui, text="(delete after done testing) used get the path to goal node", command=self.showPathToGoalNode)
        get_path.pack(side=tk.TOP, pady=5)

        #delete once we have no need for direct testing of the setup_bot function
        # setup_bot = tk.Button(self.gui, text="(delete after done testing) setup bot", command=self.controller.setupBot)
        # setup_bot.pack(side=tk.TOP, pady=5)

        #include these once we finish main logic for bot + controller
        # tk.Button(self.gui, text="start controller", command=self.controller.start).pack(side = "right")
        # tk.Button(self.gui, text="set main node", command=self.infiniteLoop).pack(side = "right")
        # tk.Button(self.gui, text="set pathing node", command=self.controller.setPathingNode).pack(side = "right")
        # tk.Button(self.gui, text="draw path and nodes", command=self.controller.drawPathAndNodes).pack(side = "right")

        #uncomment this when you actually need info from maplestory - uncomment the other block of code in main.py that has the exact same comment
        time.sleep(5) #give minimap capture thread some time to start and possibly capture a minimap frame
        is_canvas_setup = False
        while not is_canvas_setup:
            with self.sharedInfo.minimap_frame_lock:
                if self.sharedInfo.minimap_frame is not None:
                    is_canvas_setup = True
                    self.minimap_canvas_height, self.minimap_canvas_width, _ = self.sharedInfo.minimap_frame.shape
                    self.minimap_canvas = tk.Canvas(self.gui, width= self.minimap_canvas_width,
                                                    height= self.minimap_canvas_height,
                                                    background='pink',
                                                    highlightthickness=0,
                                                    borderwidth=0,
                                                    relief = 'flat')
                    self.minimap_canvas.pack(side=tk.LEFT)
                else:
                    print("failed to setup GUI due to unavailable minimap image, sleeping GUI thread for 10 seconds before trying again.")
                    time.sleep(10)

    def drawBlueNodeOnCharacter(self):
        x, y  = self.controller.getCharacterCoords()
        node_type = "Blue Node"
        self.node_count += 1
        self._printToGUIConsole(f"Identifier: {self.node_count}, Type of Node: {node_type} | Character Position: ({x},{y})")
        self.minimap_canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="lightblue", outline="lightblue", width=3, tags="node")
        self._drawNodeCount(x, y, text= self.node_count)

    def drawOrangeNodeOnCharacter(self):
        x, y = self.controller.getCharacterCoords()
        node_type = "Orange Node"
        self.node_count += 1
        self._printToGUIConsole(f"Identifier: {self.node_count}, Type of Node: {node_type} | Character Position: ({x},{y})")
        self.minimap_canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="orange", outline="darkorange", width=3, tags = "node")
        self._drawNodeCount(x, y, text = self.node_count)

    #delete once you don't need a direct way to test this. This should only exist inside the PathGraph class
    def showPathToGoalNode(self):
        print("-----------------------------------------------")
        character_coords = self.controller.getCharacterCoords()
        char_node = CharacterNode(character_coords)
        goal_node = self.controller.bot.map_rotation_order[0]
        self._drawGraph()
        self.controller.connectCharacterNode(char_node)
        self._drawGraph()
        path = self.controller.bot.pathGraph.getPathToGoalNode(char=char_node, goal=goal_node)
        if not path:
            print(f"no path found to goal node {goal_node}")
        else:
            print(f"computed path: {path} to goal node: {goal_node}")
        self.controller.deleteNode(char_node)
        # self._drawGraph()
        print("-----------------------------------------------")

    def clearGUIConsole(self):
        self.gui_console.delete(1.0, tk.END)

    #Without mocking the environment, we don't get to take advantage of _setupBot telling us it failed. We're only using this for testing purposes
    def mockSetupBotEnvironment(self):
        setup_bot_res = self.controller.bot._setupBot()
        if is_successful(setup_bot_res):
            print("setup bot successful")
        else:
            print(setup_bot_res)

    def _drawNodeCount(self, x, y, text, font=("Arial", 8, "bold")):
        # Draw outline (black border around text)
        # self.minimap_canvas.create_rectangle(x - 2, y - 5, x + 2, y - 3, fill='lightblue', outline='black')
        # Draw main number (bright color on top)
        self.minimap_canvas.create_text(x, y - 4, text=text, font=font, fill="yellow", tags="node_tag")


    #Incredibly limited custom implementation of the built-in print function. Only suitable for displaying strings and variables that have a valid string form, nothing else.
    def _printToGUIConsole(self, *args):
        seperator, end = ' ', '\n'
        # Join multiple arguments with a separator and handle non-string arguments
        strings = map(str, args)
        text = seperator.join(strings) + end
        self.gui_console.insert(tk.INSERT, text)
        self.gui_console.yview("end")
        # Also print to the IDE console for debugging

    def _clearDrawnNodesOnGUIMinimap(self):
        self.minimap_canvas.delete("node")
        self.minimap_canvas.delete("node_tag")

    def _drawGraph(self):
        graph = self.controller.getGraph()
        node_map = self.controller.getNodeMap()
        node_positions = {node: node.minimap_position for node in node_map.values()}
        nx.draw(graph, pos = node_positions, with_labels=True, node_color='blue', node_size=10, font_size=10)
        plt.gca().invert_yaxis() #invert y-axis so origin is top-left
        plt.show()

    #draws minimap on GUI
    def _updateCanvas(self):
        with self.sharedInfo.minimap_frame_lock:
            if self.sharedInfo.minimap_frame is not None:

                # Image conversion pipeline: numpy array → PIL Image → Tkinter PhotoImage
                pil_minimap = Image.fromarray(self.sharedInfo.minimap_frame)
                minimap_img = ImageTk.PhotoImage(pil_minimap)

                # Prevent garbage collection by maintaining reference
                self.minimap_canvas.image = minimap_img
                # Canvas image management: create once, update thereafter
                if self.minimap_canvas_bg_img_id is None:
                    # Initial creation: place image at canvas center
                    self.minimap_canvas_bg_img_id = self.minimap_canvas.create_image(0,
                                                                                     0,
                                                                                     image=minimap_img,
                                                                                     anchor= tk.NW)
                else:
                    # Subsequent updates: modify existing image item (preserves layer order)
                    self.minimap_canvas.itemconfig(self.minimap_canvas_bg_img_id, image=minimap_img)

        # Schedule next frame update
        self.gui.after(10, self._updateCanvas)