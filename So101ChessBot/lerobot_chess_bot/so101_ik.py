"""
SO101 IK Controller

Single point of hardware access — all reads and writes go through one lock.
Nobody outside this class should touch self.follower directly.

Usage:
    robot = SO101IKController()
    robot.connect()
    robot.move_to_home()
    robot.move_to_xyz([0.15, 0.0, 0.10])
    robot.set_gripper(45.0)
    obs = robot.get_obs()
    robot.disconnect()

With ROS2 bridge:
    bridge = ROS2BridgeClient()
    bridge.connect()
    robot = SO101IKController()
    robot.connect(bridge=bridge)
"""

from pathlib import Path
import time
import threading
import numpy as np
import pinocchio as pin
import pink
from pink import solve_ik
from pink.tasks import FrameTask, PostureTask
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

# ── Constants ─────────────────────────────────────────────────────────────────

URDF_PATH = Path(
    "robot/so101_new_calib.urdf"
).expanduser()

ACTION_KEYS = [
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
]

EE_FRAME = "gripper_tip"

HOME_DEGREES = {
  "shoulder_pan.pos": -0,
  "shoulder_lift.pos": -20,
  "elbow_flex.pos": -10,
  "wrist_flex.pos": 90,
  "wrist_roll.pos": -45,
  "gripper.pos": 0
}


class SO101IKController:
    def __init__(
        self,
        urdf_path=URDF_PATH,
        port="/dev/ttyACM0",
        move_duration=1.0,
        control_hz=50,
        robo_id="w_so101_follower",
    ):
        self.urdf_path = Path(urdf_path).expanduser()
        self.port = port
        self.move_duration = move_duration
        self.control_hz = control_hz
        self.robo_id = robo_id

        self.model, self.data = self._build_robot()
        self.follower = None
        self._q_current = None

        # Single lock for ALL hardware access
        self._hw_lock = threading.Lock()

        # Latest observation — written by bg thread, read by anyone
        self._latest_obs = None
        self._obs_ready = threading.Event()

        self._obs_thread = None
        self._running = False
        self._bridge = None

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _build_robot(self):
        model = pin.buildModelFromUrdf(str(self.urdf_path))
        data = model.createData()
        return model, data

    def connect(self, bridge=None):
        self.follower = SO101Follower(
            config=SO101FollowerConfig(
                id=self.robo_id,
                port=self.port,
                disable_torque_on_disconnect=False,
                cameras={},
            )
        )
        self.follower.connect()
        print(f"Connected to robot on {self.port}")

        self._bridge = bridge
        if bridge:
            print("ROS2 bridge attached.")

        self._running = True
        self._obs_thread = threading.Thread(target=self._obs_loop, daemon=True)
        self._obs_thread.start()

        # Wait for first observation before returning
        self._obs_ready.wait(timeout=5.0)
        print("Robot ready.")

    def disconnect(self):
        self._running = False
        if self._obs_thread:
            self._obs_thread.join(timeout=2.0)
        if self.follower:
            self.follower.disconnect()
            print("Disconnected.")

    # ── Hardware access ───────────────────────────────────────────────────────

    def _hw_read(self):
        """Read observation from hardware. Must be called with _hw_lock held."""
        return self.follower.get_observation()

    def _hw_write(self, action):
        """Write action to hardware. Must be called with _hw_lock held."""
        self.follower.send_action(action)

    # ── Background obs loop ───────────────────────────────────────────────────

    def _obs_loop(self):
        while self._running:
            try:
                with self._hw_lock:
                    obs = self._hw_read()

                self._latest_obs = obs
                self._obs_ready.set()

                if self._bridge is not None:
                    joints = {k: float(obs[k]) for k in ACTION_KEYS}
                    self._bridge.send(obs, joints)

            except Exception as e:
                print(f"[obs loop] {e}")

            time.sleep(1.0 / self.control_hz)

    def get_obs(self):
        """Get latest observation. Blocks briefly if not yet available."""
        self._obs_ready.wait(timeout=2.0)
        return self._latest_obs

    # ── Conversion ────────────────────────────────────────────────────────────

    def _deg_dict_to_rad(self, deg_dict):
        return np.array([np.deg2rad(deg_dict[k]) for k in ACTION_KEYS])

    def _rad_to_deg_dict(self, q_rad):
        return {k: float(np.rad2deg(q_rad[i])) for i, k in enumerate(ACTION_KEYS)}

    # ── FK ────────────────────────────────────────────────────────────────────

    def fk(self, deg_dict=None):
        if deg_dict is None:
            obs = self.get_obs()
            deg_dict = {k: float(obs[k]) for k in ACTION_KEYS}
        q = self._deg_dict_to_rad(deg_dict)
        pin.forwardKinematics(self.model, self.data, q)
        pin.updateFramePlacements(self.model, self.data)
        return self.data.oMf[self.model.getFrameId(EE_FRAME)]

    def get_current_xyz(self):
        return self.fk().translation.copy()

    # ── IK ────────────────────────────────────────────────────────────────────

    @staticmethod
    def rotation_pointing_down():
        """Straight down, camera facing right (-X). Used as fallback."""
        return np.array(
            [
                [-0.77, 0.666, 0],
                [-0.666, -0.77, 0],
                [0, 0, 1],
            ],
            dtype=float,
        )

    @staticmethod
    def rotation_toward_target(target_xyz, tilt_strength=0.4):
        """
        Gripper points toward target from above, camera always faces right (-X).

        tilt_strength: how much to lean toward target.
            0.0 = straight down
            0.3-0.5 is good for most boards
            1.0 = fully leaning

        Frame: +X = left, -Y = forward, +Z = up. Board to the right (-X).
        Camera faces -X (right side, away from robot base).
        """
        target = np.array(target_xyz, dtype=float)

        # Approach vector: mostly down (-Z), leaning toward target in XY
        approach = np.array(
            [
                target[0] * tilt_strength,
                target[1] * tilt_strength,
                -1.0,
            ]
        )
        z_axis = approach / np.linalg.norm(approach)

        # Camera faces -X — project perpendicular to z_axis
        camera_dir = np.array([-1.0, 0.0, 0.0])
        x_axis = camera_dir - np.dot(camera_dir, z_axis) * z_axis
        norm = np.linalg.norm(x_axis)
        if norm < 1e-6:
            x_axis = np.array([0.0, -1.0, 0.0])  # degenerate fallback
        else:
            x_axis /= norm

        y_axis = np.cross(z_axis, x_axis)
        y_axis /= np.linalg.norm(y_axis)

        return np.column_stack([x_axis, y_axis, z_axis])

    def _solve_ik(self, q_seed_rad, target_xyz, rotation=None):
        rot = rotation if rotation is not None else np.eye(3)
        orientation_cost = 0.5 if rotation is not None else 0.0
        target_pose = pin.SE3(rot, np.array(target_xyz, dtype=float))
        configuration = pink.Configuration(self.model, self.data, q_seed_rad)

        ee_task = FrameTask(
            EE_FRAME, position_cost=1.0, orientation_cost=orientation_cost
        )
        ee_task.set_target(target_pose)

        posture_task = PostureTask(cost=1e-3)
        posture_task.set_target(q_seed_rad)

        dt = 0.001
        for _ in range(5000):
            velocity = solve_ik(
                configuration, [ee_task, posture_task], dt, solver="quadprog"
            )
            configuration.integrate_inplace(velocity, dt)
            err = np.linalg.norm(ee_task.compute_error(configuration))
            if err < 1e-4:
                break

        return configuration.q, err

    # ── Motion primitives ─────────────────────────────────────────────────────

    def _send_joints(self, deg_dict):
        """Send joint positions to hardware through the lock."""
        with self._hw_lock:
            self._hw_write(deg_dict)

    def _interpolate_and_send(self, q_start_deg, q_target_deg, duration=None):
        dur = duration or self.move_duration
        steps = int(dur * self.control_hz)
        for step in range(steps + 1):
            alpha = step / steps
            interp = {
                k: q_start_deg[k] + alpha * (q_target_deg[k] - q_start_deg[k])
                for k in q_start_deg
            }
            self._send_joints(interp)
            time.sleep(1.0 / self.control_hz)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_gripper(self, degrees, duration=0.5):
        """
        Set gripper to a position in degrees.
        Keeps all other joints at their current position.
        """
        obs = self.get_obs()
        current = {k: float(obs[k]) for k in ACTION_KEYS}
        target = current.copy()
        target["gripper.pos"] = degrees
        self._interpolate_and_send(current, target, duration=duration)

    def move_to_home(self, home=HOME_DEGREES, duration=3.0):
        obs = self.get_obs()
        current_deg = {k: float(obs[k]) for k in ACTION_KEYS}
        self._interpolate_and_send(current_deg, home, duration=duration)
        self._q_current = self._deg_dict_to_rad(home)
        print("At home.")

    def move_to_joints(self, deg_dict, duration=None):
        """Move directly to a joint configuration in degrees."""
        obs = self.get_obs()
        current_deg = {k: float(obs[k]) for k in ACTION_KEYS}
        self._interpolate_and_send(current_deg, deg_dict, duration=duration)

    def move_to_xyz(
        self,
        target_xyz,
        rotation=None,
        duration=None,
        pos_tolerance=3.0,
        approach_z_offset=0.06,
        approach_if_unreachable=True,
    ):
        """
        Solve IK and move to target_xyz.

        If position error exceeds pos_tolerance with orientation constraint:
          1. Move to approach position (same XY, raised by approach_z_offset)
             with orientation constraint — gets base/arm in right neighborhood
          2. From there, solve final position without orientation constraint
             so wrist extends naturally to reach target

        Returns True if final IK converged within pos_tolerance mm.
        """
        obs = self.get_obs()
        current_deg = {k: float(obs[k]) for k in ACTION_KEYS}
        q_seed = self._deg_dict_to_rad(current_deg)
        target_xyz = list(target_xyz)

        print(f"Solving IK for {[f'{v:.4f}' for v in target_xyz]} ...")
        q_solution, _ = self._solve_ik(q_seed, target_xyz, rotation=rotation)

        pin.forwardKinematics(self.model, self.data, q_solution)
        pin.updateFramePlacements(self.model, self.data)
        achieved = self.data.oMf[self.model.getFrameId(EE_FRAME)].translation
        pos_error = np.linalg.norm(achieved - np.array(target_xyz)) * 1000

        if pos_error > pos_tolerance and rotation is not None:
            if approach_if_unreachable:
                print(f"  error: {pos_error:.1f}mm — moving to approach first")

                # Step 1: move to approach (raised Z) with orientation constraint
                approach_xyz = [
                    target_xyz[0],
                    target_xyz[1],
                    target_xyz[2] + approach_z_offset,
                ]
                q_approach, _ = self._solve_ik(q_seed, approach_xyz, rotation=rotation)
                q_approach_deg = self._rad_to_deg_dict(q_approach)
                self._interpolate_and_send(
                    current_deg, q_approach_deg, duration=duration
                )
                current_deg = q_approach_deg
                self._q_current = q_approach

            # Step 2: from approach, solve final without orientation constraint
            print(f"  Solving final without orientation constraint...")
            q_solution, _ = self._solve_ik(
                q_approach if approach_if_unreachable else q_seed,
                target_xyz,
                rotation=None,
            )
            pin.forwardKinematics(self.model, self.data, q_solution)
            pin.updateFramePlacements(self.model, self.data)
            achieved = self.data.oMf[self.model.getFrameId(EE_FRAME)].translation
            pos_error = np.linalg.norm(achieved - np.array(target_xyz)) * 1000
            print(f"  final error: {pos_error:.1f}mm  achieved: {achieved.round(4)}")

            q_solution_deg = self._rad_to_deg_dict(q_solution)
            self._interpolate_and_send(current_deg, q_solution_deg, duration=duration)
        else:
            print(f"  error: {pos_error:.1f}mm  achieved: {achieved.round(4)}")
            q_solution_deg = self._rad_to_deg_dict(q_solution)
            self._interpolate_and_send(current_deg, q_solution_deg, duration=duration)

        if pos_error > pos_tolerance:
            print(f"  WARNING: poor convergence ({pos_error:.1f}mm)")

        self._q_current = q_solution
        return pos_error < pos_tolerance


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    robot = SO101IKController()
    robot.connect()

    try:
        robot.move_to_home()
        print(f"XYZ: {robot.get_current_xyz()}")
        robot.move_to_xyz([-0.12669, -0.16338, 0.07743])
        robot.set_gripper(45.0)
        robot.set_gripper(5.0)
    except KeyboardInterrupt:
        print("Interrupted.")
    finally:
        robot.move_to_home()
        robot.disconnect()
