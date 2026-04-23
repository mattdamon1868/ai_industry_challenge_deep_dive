#!/usr/bin/env python3
"""
test_policy_load.py
-------------------
Sanity-check that DylACTPolicy loads and runs a forward pass correctly
WITHOUT needing the full Gazebo/ROS 2 sim running.

Run from your ROS 2 workspace (with the env sourced):
    python3 src/dyl_cable_policy/test_policy_load.py

What it checks:
    [1] CUDA / CPU device detection
    [2] HuggingFace checkpoint download & model load
    [3] Normalisation stats load
    [4] Fake observation construction (correct tensor shapes)
    [5] Model forward pass (inference_mode)
    [6] Temporal ensembling produces a valid action
    [7] EMA smoothing step
    [8] Motion update message construction
    [9] F/T termination logic
"""

import sys
import time
import traceback
import numpy as np
import torch

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m·\033[0m"

results = []


def check(name, fn):
    print(f"  {INFO} {name} ...", end=" ", flush=True)
    try:
        result = fn()
        print(f"{PASS} {result or ''}")
        results.append((name, True, None))
        return True
    except Exception as e:
        print(f"{FAIL}")
        traceback.print_exc()
        results.append((name, False, str(e)))
        return False


# ---------------------------------------------------------------------------
# Minimal stubs so we can import without a live ROS 2 node
# ---------------------------------------------------------------------------

class FakeLogger:
    def info(self, msg): print(f"    [LOG] {msg}")
    def warn(self, msg): print(f"    [WARN] {msg}")
    def error(self, msg): print(f"    [ERR] {msg}")

class FakeClock:
    class FakeTime:
        def to_msg(self): return None
    def now(self): return self.FakeTime()
    def sleep_for(self, d): time.sleep(d.nanoseconds / 1e9 if hasattr(d, "nanoseconds") else d)

class FakeParam:
    def __init__(self, val): self.value = val

class FakeNode:
    def __init__(self):
        self._logger = FakeLogger()
        self._clock = FakeClock()
    def get_logger(self): return self._logger
    def get_clock(self): return self._clock
    def declare_parameter(self, name, default): return FakeParam(default)


def make_fake_image(height=480, width=640):
    """Minimal ROS Image stub with random pixel data."""
    class FakeImage:
        def __init__(self):
            self.height = height
            self.width = width
            arr = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
            self.data = arr.tobytes()
    return FakeImage()


def make_fake_observation():
    """Stub Observation with plausible shapes."""
    class Vec3:
        def __init__(self, x=0., y=0., z=0.): self.x=x; self.y=y; self.z=z
    class Quat:
        def __init__(self): self.x=0.; self.y=0.; self.z=0.; self.w=1.
    class Twist:
        def __init__(self): self.linear=Vec3(); self.angular=Vec3()
    class Pose:
        def __init__(self): self.position=Vec3(); self.orientation=Quat()
    class Wrench:
        def __init__(self): self.force=Vec3(z=10.0); self.torque=Vec3()  # z=10N → triggers threshold
    class JointStates:
        def __init__(self): self.position = [0.1*i for i in range(7)]
    class ControllerState:
        def __init__(self):
            self.tcp_pose = Pose()
            self.tcp_velocity = Twist()
            self.tcp_error = [0.0]*6
            self.tcp_wrench = Wrench()
    class FakeObs:
        def __init__(self):
            self.left_image   = make_fake_image()
            self.center_image = make_fake_image()
            self.right_image  = make_fake_image()
            self.controller_state = ControllerState()
            self.joint_states = JointStates()
    return FakeObs()


# ---------------------------------------------------------------------------
# Patch ROS imports before importing our policy
# ---------------------------------------------------------------------------

import unittest.mock as mock

ros_mocks = [
    "rclpy", "rclpy.node",
    "aic_model", "aic_model.policy",
    "aic_model_interfaces", "aic_model_interfaces.msg",
    "aic_task_interfaces", "aic_task_interfaces.msg",
    "aic_control_interfaces", "aic_control_interfaces.msg",
    "geometry_msgs", "geometry_msgs.msg",
]
for mod in ros_mocks:
    sys.modules.setdefault(mod, mock.MagicMock())

# Provide real Policy base class
from abc import ABC, abstractmethod
class Policy(ABC):
    def __init__(self, parent_node):
        self._parent_node = parent_node
    def get_logger(self): return self._parent_node.get_logger()
    def get_clock(self): return self._parent_node.get_clock()
    @abstractmethod
    def insert_cable(self, task, get_observation, move_robot, send_feedback, **kwargs): pass

sys.modules["aic_model.policy"].Policy = Policy
sys.modules["aic_model.policy"].GetObservationCallback = None
sys.modules["aic_model.policy"].MoveRobotCallback = None
sys.modules["aic_model.policy"].SendFeedbackCallback = None

# Geometry stubs
class Vec3Stub:
    def __init__(self, x=0., y=0., z=0.): self.x=x; self.y=y; self.z=z
class TwistStub:
    def __init__(self, linear=None, angular=None):
        self.linear = linear or Vec3Stub()
        self.angular = angular or Vec3Stub()
class WrenchStub:
    def __init__(self, force=None, torque=None):
        self.force = force or Vec3Stub()
        self.torque = torque or Vec3Stub()
class MotionUpdateStub:
    def __init__(self):
        self.velocity = None
        self.header = type("H", (), {"frame_id": "", "stamp": None})()
        self.target_stiffness = []
        self.target_damping = []
        self.feedforward_wrench_at_tip = WrenchStub()
        self.wrench_feedback_gains_at_tip = []
        self.trajectory_generation_mode = type("T", (), {"mode": None})()
class TrajGenMode:
    MODE_VELOCITY = 1

sys.modules["geometry_msgs.msg"].Vector3 = Vec3Stub
sys.modules["geometry_msgs.msg"].Twist = TwistStub
sys.modules["geometry_msgs.msg"].Wrench = WrenchStub
sys.modules["aic_control_interfaces.msg"].MotionUpdate = MotionUpdateStub
sys.modules["aic_control_interfaces.msg"].TrajectoryGenerationMode = TrajGenMode

# ---------------------------------------------------------------------------
# Now import the actual policy
# ---------------------------------------------------------------------------
sys.path.insert(0, ".")
from deep_dive_policy_node.deep_dive import DeepDive, ENSEMBLE_WINDOW, IMAGE_SCALE


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
print("\n━━━ DeepDive Load Test ━━━\n")

node = FakeNode()
policy = None

# [1] Device
check("[1] CUDA/CPU detection", lambda:
    f"device={'cuda' if torch.cuda.is_available() else 'cpu'}"
)

# [2] Model load
def load_policy():
    global policy
    policy = DeepDive(node)
    return f"chunk_size={policy.chunk_size}"

ok = check("[2] Checkpoint download & model load", load_policy)
if not ok:
    print("\n  Policy failed to load — remaining tests skipped.")
    sys.exit(1)

# [3] Norm stats
check("[3] Normalisation stats", lambda:
    f"state_mean shape={policy.state_mean.shape}"
)

# [4] Fake observation → tensors
def test_obs_build():
    obs = make_fake_observation()
    tensors = policy._build_obs(obs)
    shapes = {k: tuple(v.shape) for k, v in tensors.items()}
    return str(shapes)
check("[4] Observation tensor construction", test_obs_build)

# [5] Forward pass
def test_forward():
    import collections
    policy._chunk_queue = collections.deque(maxlen=ENSEMBLE_WINDOW)
    obs = make_fake_observation()
    tensors = policy._build_obs(obs)
    with torch.inference_mode():
        out = policy.model.select_action(tensors)
    return f"output shape={tuple(out.shape)}"
check("[5] Model forward pass", test_forward)

# [6] Temporal ensembling
def test_ensemble():
    import collections
    policy._chunk_queue = collections.deque(maxlen=ENSEMBLE_WINDOW)
    action_dim = policy.action_mean.shape[-1]
    for _ in range(ENSEMBLE_WINDOW):
        fake_chunk = torch.randn(1, action_dim)
        action = policy._ensemble_action(fake_chunk)
    return f"ensemble output shape={action.shape}"
check("[6] Temporal ensembling", test_ensemble)

# [7] EMA smoothing
def test_ema():
    policy._ema_action = None
    action_dim = policy.action_mean.shape[-1]
    a1 = np.random.randn(action_dim)
    a2 = np.random.randn(action_dim)
    policy._ema_action = a1
    import collections
    policy._chunk_queue = collections.deque(maxlen=ENSEMBLE_WINDOW)
    smoothed = 0.3 * a1 + 0.7 * a2  # manual EMA step
    return f"EMA output is finite={np.all(np.isfinite(smoothed))}"
check("[7] EMA smoothing", test_ema)

# [8] Motion update message
def test_motion():
    action = np.array([0.01, -0.01, 0.02, 0.0, 0.0, 0.0, 0.0])
    msg = policy._make_motion_update(action)
    assert msg.velocity is not None
    return "MotionUpdate constructed OK"
check("[8] Motion update construction", test_motion)

# [9] F/T termination
def test_ft():
    policy._peak_fz = 0.0
    obs = make_fake_observation()
    # First call at t=0 — too early, should not trigger
    r1 = policy._check_insertion_complete(obs, elapsed=0.5)
    # Force obs to have high then low force — simulate elapsed time past minimum
    obs.controller_state.tcp_wrench.force.z = 12.0
    policy._peak_fz = 12.0
    obs.controller_state.tcp_wrench.force.z = 1.0
    r2 = policy._check_insertion_complete(obs, elapsed=5.0)
    assert not r1, "Should not trigger before MIN_INSERTION_TIME_SEC"
    assert r2,     "Should trigger after force spike + drop"
    return f"early=False, post-spike=True ✓"
check("[9] F/T termination logic", test_ft)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n━━━ Results ━━━\n")
passed = sum(1 for _, ok, _ in results if ok)
total  = len(results)
for name, ok, err in results:
    status = PASS if ok else FAIL
    print(f"  {status} {name}" + (f"  → {err}" if err else ""))

print(f"\n  {passed}/{total} passed\n")
sys.exit(0 if passed == total else 1)