import os

import git
import magnum as mn
import pickle
import habitat_sim
from habitat_sim.utils import viz_utils as vut

try:
    import ipywidgets as widgets
    from IPython.display import display as ipydisplay

    # For using jupyter/ipywidget IO components

    HAS_WIDGETS = True
except ImportError:
    HAS_WIDGETS = False

repo = git.Repo(".", search_parent_directories=True)
dir_path = repo.working_tree_dir
data_path = os.path.join(dir_path, "data")
output_path = os.path.join(
    dir_path, "examples/tutorials/replica_cad_output/"
)  # @param {type:"string"}
os.makedirs(output_path, exist_ok=True)

# define some globals the first time we run.
if "sim" not in globals():
    global sim
    sim = None
    global obj_attr_mgr
    obj_attr_mgr = None
    global stage_attr_mgr
    stage_attr_mgr = None
    global rigid_obj_mgr
    rigid_obj_mgr = None


# %%
# @title Define Configuration Utility Functions { display-mode: "form" }
# @markdown (double click to show code)

# @markdown This cell defines a number of utility functions used throughout the tutorial to make simulator reconstruction easy:
# @markdown - make_cfg
# @markdown - make_default_settings
# @markdown - make_simulator_from_settings


def make_cfg(settings):
    sim_cfg = habitat_sim.SimulatorConfiguration()
    sim_cfg.gpu_device_id = 0
    sim_cfg.scene_dataset_config_file = settings["scene_dataset"]
    sim_cfg.scene_id = settings["scene"]
    sim_cfg.enable_physics = settings["enable_physics"]
    # Specify the location of the scene dataset
    if "scene_dataset_config" in settings:
        sim_cfg.scene_dataset_config_file = settings["scene_dataset_config"]
    if "override_scene_light_defaults" in settings:
        sim_cfg.override_scene_light_defaults = settings[
            "override_scene_light_defaults"
        ]
    if "scene_light_setup" in settings:
        sim_cfg.scene_light_setup = settings["scene_light_setup"]

    # Note: all sensors must have the same resolution
    sensor_specs = []
    color_sensor_1st_person_spec = habitat_sim.CameraSensorSpec()
    color_sensor_1st_person_spec.uuid = "color_sensor_1st_person"
    color_sensor_1st_person_spec.sensor_type = habitat_sim.SensorType.COLOR
    color_sensor_1st_person_spec.resolution = [
        settings["height"],
        settings["width"],
    ]
    color_sensor_1st_person_spec.position = [0.0, settings["sensor_height"], 0.0]
    color_sensor_1st_person_spec.orientation = [
        settings["sensor_pitch"],
        0.0,
        0.0,
    ]
    color_sensor_1st_person_spec.sensor_subtype = habitat_sim.SensorSubType.PINHOLE
    sensor_specs.append(color_sensor_1st_person_spec)

    depth_sensor_spec = habitat_sim.CameraSensorSpec()
    depth_sensor_spec.uuid = "depth_sensor"
    depth_sensor_spec.sensor_type = habitat_sim.SensorType.DEPTH
    depth_sensor_spec.resolution = [settings["height"], settings["width"]]
    depth_sensor_spec.position = [0.0, settings["sensor_height"], 0.0]
    depth_sensor_spec.sensor_subtype = habitat_sim.SensorSubType.PINHOLE
    sensor_specs.append(depth_sensor_spec)

    semantic_sensor_spec = habitat_sim.CameraSensorSpec()
    semantic_sensor_spec.uuid = "semantic_sensor"
    semantic_sensor_spec.sensor_type = habitat_sim.SensorType.SEMANTIC
    semantic_sensor_spec.resolution = [settings["height"], settings["width"]]
    semantic_sensor_spec.position = [0.0, settings["sensor_height"], 0.0]
    semantic_sensor_spec.sensor_subtype = habitat_sim.SensorSubType.PINHOLE
    sensor_specs.append(semantic_sensor_spec)

    # Here you can specify the amount of displacement in a forward action and the turn angle
    agent_cfg = habitat_sim.agent.AgentConfiguration()
    agent_cfg.sensor_specifications = sensor_specs

    return habitat_sim.Configuration(sim_cfg, [agent_cfg])


def make_default_settings():
    rgb_sensor = True  # @param {type:"boolean"}
    depth_sensor = True  # @param {type:"boolean"}
    semantic_sensor = True  # @param {type:"boolean"}
    settings = {
        "width": 1280,  # Spatial resolution of the observations
        "height": 720,
        "scene_dataset": os.path.join(
            data_path, "replica_cad/replicaCAD.scene_dataset_config.json"
        ),  # dataset path
        "scene": "NONE",  # Scene path
        "default_agent": 0,
        "sensor_height": 1.5,  # Height of sensors in meters
        "sensor_pitch": 0.0,  # sensor pitch (x rotation in rads)
        "color_sensor": rgb_sensor,  # RGB sensor
        "depth_sensor": depth_sensor,  # Depth sensor
        "semantic_sensor": semantic_sensor,  # Semantic sensor
        "seed": 1,
        "enable_physics": True,  # enable dynamics simulation
    }
    return settings


def make_simulator_from_settings(sim_settings):
    cfg = make_cfg(sim_settings)
    # clean-up the current simulator instance if it exists
    global sim
    global obj_attr_mgr
    global prim_attr_mgr
    global stage_attr_mgr
    global rigid_obj_mgr
    global metadata_mediator

    if sim != None:
        sim.close()
    # initialize the simulator
    sim = habitat_sim.Simulator(cfg)
    # Managers of various Attributes templates
    obj_attr_mgr = sim.get_object_template_manager()
    obj_attr_mgr.load_configs(str(os.path.join(data_path, "objects/example_objects")))
    prim_attr_mgr = sim.get_asset_template_manager()
    stage_attr_mgr = sim.get_stage_template_manager()
    # Manager providing access to rigid objects
    rigid_obj_mgr = sim.get_rigid_object_manager()
    # get metadata_mediator
    metadata_mediator = sim.metadata_mediator

    # UI-populated handles used in various cells.  Need to initialize to valid
    # value in case IPyWidgets are not available.
    # Holds the user's desired scene handle
    global selected_scene
    selected_scene = "NONE"


# [/setup]


# %%
# @title Define Simulation Utility Function { display-mode: "form" }
# @markdown (double click to show code)
def simulate(sim, dt=1.0, get_frames=True):
    # simulate dt seconds at 60Hz to the nearest fixed timestep
    print("Simulating {:.3f} world seconds.".format(dt))
    observations = []
    start_time = sim.get_world_time()
    while sim.get_world_time() < start_time + dt:
        sim.step_physics(1.0 / 60.0)
        if get_frames:
            observations.append(sim.get_sensor_observations())
    return observations


# %%
# @title Define GUI Utility Functions { display-mode: "form" }
# @markdown (double click to show code)

# @markdown This cell provides utility functions to build and manage IPyWidget interactive components.


# Event handler for dropdowns displaying file-based object handles
def on_scene_ddl_change(ddl_values):
    global selected_scene
    selected_scene = ddl_values["new"]
    return selected_scene


# Build a dropdown list holding obj_handles and set its event handler
def set_handle_ddl_widget(scene_handles, sel_handle, on_change):
    descStr = "Available Scenes:"
    style = {"description_width": "300px"}
    obj_ddl = widgets.Dropdown(
        options=scene_handles,
        value=sel_handle,
        description=descStr,
        style=style,
        disabled=False,
        layout={"width": "max-content"},
    )

    obj_ddl.observe(on_change, names="value")
    return obj_ddl, sel_handle


def set_button_launcher(desc):
    button = widgets.Button(
        description=desc,
        layout={"width": "max-content"},
    )
    return button


# Builds widget-based UI components
def build_widget_ui(metadata_mediator):
    # Holds the user's desired scene
    global selected_scene

    # All file-based object template handles
    scene_handles = metadata_mediator.get_scene_handles()
    # Set default as first available valid handle, or NONE scene if none are available
    if len(scene_handles) == 0:
        selected_scene = "NONE"
    else:
        # Set default selection to be first valid non-NONE scene (for python consumers)
        for scene_handle in scene_handles:
            if "NONE" not in scene_handle:
                selected_scene = scene_handle
                break

    if not HAS_WIDGETS:
        # If no widgets present, return, using default
        return

    # Construct DDLs and assign event handlers
    # Build widgets
    scene_obj_ddl, selected_scene = set_handle_ddl_widget(
        scene_handles,
        selected_scene,
        on_scene_ddl_change,
    )

    # Display DDLs
    ipydisplay(scene_obj_ddl)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--no-display", dest="display", action="store_false")
    parser.add_argument("--no-make-video", dest="make_video", action="store_false")
    parser.set_defaults(show_video=True, make_video=True)
    args, _ = parser.parse_known_args()
    show_video = args.display
    display = args.display
    make_video = args.make_video
else:
    show_video = False
    make_video = False
    display = False

from PIL import Image
import numpy as np
from matplotlib import pyplot as plt
# Change to do something like this maybe: https://stackoverflow.com/a/41432704
def save_sample(rgb_obs, semantic_obs, depth_obs, idx, save_path=dir_path + '/output'):
    from habitat_sim.utils.common import d3_40_colors_rgb

    # Create and save the RGB image
    rgb_img = Image.fromarray(rgb_obs, mode="RGBA")
    rgb_img.save(f"{save_path}/rgb_image_{idx}.png")

    # Create and save the semantic image
    semantic_img = Image.new("P", (semantic_obs.shape[1], semantic_obs.shape[0]))
    semantic_img.putpalette(d3_40_colors_rgb.flatten())
    semantic_img.putdata((semantic_obs.flatten() % 40).astype(np.uint8))
    semantic_img = semantic_img.convert("RGBA")
    semantic_img.save(f"{save_path}/semantic_image_{idx}.png")

    # Create and save the depth image
    depth_img = Image.fromarray((depth_obs / 10 * 255).astype(np.uint8), mode="L")
    depth_img.save(f"{save_path}/depth_image_{idx}.png")

# %% [markdown]
# # View ReplicaCAD in Habitat-sim
# Use the code in this section to view assets in the Habitat-sim engine.

# %%
# [initialize]
# @title Initialize Simulator{ display-mode: "form" }

sim_settings = make_default_settings()
make_simulator_from_settings(sim_settings)
# [/initialize]

# %%
# @title Select a SceneInstance: { display-mode: "form" }
# @markdown Select a scene from the dropdown and then run the next cell to load and simulate that scene and produce a visualization of the result.

build_widget_ui(sim.metadata_mediator)

# %% [markdown]
# ## Load the Select Scene and Simulate!
# This cell will load the scene selected above, simulate, and produce a visualization.

# %%
global selected_scene
if sim_settings["scene"] != selected_scene:
    sim_settings["scene"] = selected_scene
    make_simulator_from_settings(sim_settings)

observations = []
translations = []
rotations = []
start_time = sim.get_world_time()
count = 1
sim.agents[0].scene_node.translation = mn.Vector3([-2, 0, 0])
while sim.get_world_time() < start_time + 4.0:
    if count < 40:
        sim.agents[0].scene_node.rotate(mn.Rad(- mn.math.pi_half / 20.0), mn.Vector3(0, 1, 0))
    elif count < 60:
        sim.agents[0].scene_node.translation += np.array([0.3, 0, 0])
        sim.agents[0].scene_node.rotate(mn.Rad(- mn.math.pi_half / 20.0), mn.Vector3(0, 1, 0))
    elif count < 80:
        sim.agents[0].scene_node.translation += np.array([0.0, 0, 0.3])
        sim.agents[0].scene_node.rotate(mn.Rad(- mn.math.pi_half / 20.0), mn.Vector3(0, 1, 0))
    else:
        sim.agents[0].scene_node.translation += np.array([-0.1, 0, -0.1])
    sim.step_physics(1.0 / 30.0)
    if make_video:
        observation = sim.get_sensor_observations()
        observations.append(observation)
        rgb = observation["color_sensor_1st_person"]
        semantic = observation["semantic_sensor"]
        depth = observation["depth_sensor"]
        translation = sim.agents[0].scene_node.translation
        rotation = sim.agents[0].scene_node.rotation
        translations.append(translation)
        rotations.append(rotation)
        if display:
            save_sample(rgb, semantic, depth, count)
            count +=1 
            
# Save to pickle
width, height = sim_settings['width'], sim_settings['height']
fov = float(sim.agents[0]._sensors['color_sensor_1st_person'].hfov)
fx = fy = 0.5 * width / np.tan(np.radians(fov) / 2)
cx, cy = width / 2, height / 2
camera_info = {"width": width, "height": height, "fov": fov, "fx": fx, "fy": fy, "cx": cx, "cy": cy}
data_to_save = {
    "observations": observations,
    "rotations": rotations,
    "translations": translations,
    "camera_info": camera_info
}

output_filename = dir_path + '/output/data.pkl'
with open(output_filename, "wb") as file:
    pickle.dump(data_to_save, file)

print(f"Data saved to {output_filename}")
