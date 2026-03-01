import meshcat.geometry as mg
import meshcat.transformations as mt

from pathlib import Path
import numpy as np
import pinocchio as pin
from pinocchio.visualize import MeshcatVisualizer

URDF_PATH = Path("robot/so101_new_calib.urdf").expanduser()
MESH_DIR = str(URDF_PATH.parent)  # STL files are in assets/ relative to the URDF

ACTION_KEYS = [
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
]
# FLIPPED_JOINTS = {"shoulder_lift.pos"}

HOME_DEGREES = {
    "shoulder_pan.pos": -0.5886052534221307,
    "shoulder_lift.pos": -0.0,
    "elbow_flex.pos": 0.54730647351744,
    "wrist_flex.pos": 0.59067357512953,
    "wrist_roll.pos": 0.18803418803418,
    "gripper.pos": 0.791765637371338,
}


def degrees_to_rad(deg_dict):
    result = []
    for k in ACTION_KEYS:
        val = deg_dict[k]
        # if k in FLIPPED_JOINTS:
        #     val = -val
        result.append(np.deg2rad(val))
    return np.array(result)


# Load model with visuals
model, collision_model, visual_model = pin.buildModelsFromUrdf(str(URDF_PATH), MESH_DIR)
data = model.createData()

viz = MeshcatVisualizer(model, collision_model, visual_model)
viz.initViewer(open=True)
viz.loadViewerModel()

q = degrees_to_rad(HOME_DEGREES)
viz.display(q)

# Compute FK to get gripper_tip position
pin.forwardKinematics(model, data, q)
pin.updateFramePlacements(model, data)
tip_id = model.getFrameId("gripper_tip")
tip_pose = data.oMf[tip_id]

# Add a red sphere at gripper_tip
viz.viewer["gripper_tip"].set_object(
    mg.Sphere(0.01), mg.MeshLambertMaterial(color=0xFF0000)  # 1cm radius sphere
)

# Set its transform
T = np.eye(4)
T[:3, :3] = tip_pose.rotation
T[:3, 3] = tip_pose.translation
viz.viewer["gripper_tip"].set_transform(T)

print(f"Gripper tip position: {tip_pose.translation}")

print("Displaying home position. Open the browser URL above.")
print("Call viz.display(q) with different configs to inspect poses.")

# Keep alive so you can inspect
input("Press Enter to exit...")
