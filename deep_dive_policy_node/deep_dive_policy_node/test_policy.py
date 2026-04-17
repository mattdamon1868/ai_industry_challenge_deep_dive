#
# dyl_cable_policy/policy.py
#
# ACT-based cable insertion policy with:
#   - Temporal ensembling (free accuracy boost, no retraining needed)
#   - F/T-based early termination (detect successful insertion)
#   - Action smoothing (EMA filter on outputs)
#   - Clean structure for future fine-tuning / F/T state augmentation
#

import os
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

import time
import json
import collections
import numpy as np
import cv2
import torch
import draccus
from pathlib import Path
from typing import Dict

from rclpy.node import Node
from geometry_msgs.msg import Twist, Vector3, Wrench

from aic_model.policy import (
    GetObservationCallback,
    MoveRobotCallback,
    Policy,
    SendFeedbackCallback,
)
from aic_model_interfaces.msg import Observation
from aic_task_interfaces.msg import Task
from aic_control_interfaces.msg import MotionUpdate, TrajectoryGenerationMode

from lerobot.policies.act.modeling_act import ACTPolicy
from lerobot.policies.act.configuration_act import ACTConfig
from safetensors.torch import load_file
from huggingface_hub import snapshot_download


# ---------------------------------------------------------------------------
# Tuneable constants — adjust without touching the core logic
# ---------------------------------------------------------------------------

# HuggingFace repo. Swap to your fine-tuned checkpoint when ready.
HF_REPO_ID = "grkw/aic_act_policy"

# Image downscale factor. 0.25 = quarter-res (matches training). 0.5 = better quality.
IMAGE_SCALE = 0.25

# Control loop target frequency (Hz)
CONTROL_HZ = 10.0

# Maximum run time per insertion attempt (seconds)
MAX_DURATION_SEC = 30.0

# --- Temporal Ensembling ---
# How many recent action chunks to ensemble over.
# Higher = smoother but more lag. 4-8 is a good starting range.
ENSEMBLE_WINDOW = 5

# Exponential weighting for ensembling: newer predictions weighted higher.
# w_k = exp(-ENSEMBLE_DECAY * k), k=0 is the most recent.
ENSEMBLE_DECAY = 0.1

# --- Action Smoothing (EMA) ---
# 0.0 = no smoothing (raw output), 1.0 = completely frozen (useless).
# 0.3 means 30% previous + 70% new action.
EMA_ALPHA = 0.3

# --- F/T Termination ---
# If Z-axis force exceeds this (Newtons) AND then drops below EXIT_FORCE_DROP,
# we interpret it as successful plug seating.
INSERTION_FORCE_THRESHOLD_N = 8.0
INSERTION_FORCE_DROP_N = 3.0

# Minimum time before F/T termination is evaluated (avoid false positives at start)
MIN_INSERTION_TIME_SEC = 2.0


class DylACTPolicy(Policy):
    """
    Cable insertion policy based on LeRobot ACT with temporal ensembling.

    To use a fine-tuned checkpoint: set HF_REPO_ID at the top of this file
    to point at your model, or pass repo_id as a ROS param.
    """

    def __init__(self, parent_node: Node):
        super().__init__(parent_node)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.get_logger().info(f"DylACTPolicy init | device={self.device}")

        # -----------------------------------------------------------------------
        # Load model
        # -----------------------------------------------------------------------
        repo_id = parent_node.declare_parameter("hf_repo_id", HF_REPO_ID).value
        self.get_logger().info(f"Downloading checkpoint: {repo_id}")

        policy_path = Path(
            snapshot_download(
                repo_id=repo_id,
                allow_patterns=["config.json", "*.safetensors"],
            )
        )

        with open(policy_path / "config.json", "r") as f:
            config_dict = json.load(f)
            config_dict.pop("type", None)  # draccus doesn't know this field

        config = draccus.decode(ACTConfig, config_dict)
        self.chunk_size = config.chunk_size  # needed for ensembling

        self.model = ACTPolicy(config)
        self.model.load_state_dict(load_file(policy_path / "model.safetensors"))
        self.model.eval().to(self.device)
        self.get_logger().info(f"Model loaded | chunk_size={self.chunk_size}")

        # -----------------------------------------------------------------------
        # Normalisation stats
        # -----------------------------------------------------------------------
        stats = load_file(
            policy_path / "policy_preprocessor_step_3_normalizer_processor.safetensors"
        )

        def stat(key, shape):
            return stats[key].to(self.device).view(*shape)

        self.img_stats = {
            cam: {
                "mean": stat(f"observation.images.{cam}_camera.mean", (1, 3, 1, 1)),
                "std":  stat(f"observation.images.{cam}_camera.std",  (1, 3, 1, 1)),
            }
            for cam in ("left", "center", "right")
        }
        self.state_mean = stat("observation.state.mean", (1, -1))
        self.state_std  = stat("observation.state.std",  (1, -1))
        self.action_mean = stat("action.mean", (1, -1))
        self.action_std  = stat("action.std",  (1, -1))

        self.get_logger().info("Normalisation stats loaded.")

    # ---------------------------------------------------------------------------
    # Image helper
    # ---------------------------------------------------------------------------
    @staticmethod
    def _img_to_tensor(raw_img, device, scale, mean, std) -> torch.Tensor:
        img_np = np.frombuffer(raw_img.data, dtype=np.uint8).reshape(
            raw_img.height, raw_img.width, 3
        )
        if scale != 1.0:
            img_np = cv2.resize(img_np, None, fx=scale, fy=scale,
                                interpolation=cv2.INTER_AREA)
        t = (
            torch.from_numpy(img_np)
            .permute(2, 0, 1).float().div(255.0).unsqueeze(0).to(device)
        )
        return (t - mean) / std

    # ---------------------------------------------------------------------------
    # Observation builder
    # ---------------------------------------------------------------------------
    def _build_obs(self, obs_msg: Observation) -> Dict[str, torch.Tensor]:
        obs = {}
        for cam in ("left", "center", "right"):
            img = getattr(obs_msg, f"{cam}_image")
            obs[f"observation.images.{cam}_camera"] = self._img_to_tensor(
                img, self.device, IMAGE_SCALE,
                self.img_stats[cam]["mean"], self.img_stats[cam]["std"],
            )

        tcp = obs_msg.controller_state.tcp_pose
        vel = obs_msg.controller_state.tcp_velocity
        state_np = np.array([
            tcp.position.x, tcp.position.y, tcp.position.z,
            tcp.orientation.x, tcp.orientation.y, tcp.orientation.z, tcp.orientation.w,
            vel.linear.x, vel.linear.y, vel.linear.z,
            vel.angular.x, vel.angular.y, vel.angular.z,
            *obs_msg.controller_state.tcp_error,
            *obs_msg.joint_states.position[:7],
        ], dtype=np.float32)

        raw = torch.from_numpy(state_np).float().unsqueeze(0).to(self.device)
        obs["observation.state"] = (raw - self.state_mean) / self.state_std
        return obs

    # ---------------------------------------------------------------------------
    # Temporal ensembling
    # ---------------------------------------------------------------------------
    def _ensemble_action(self, new_chunk: torch.Tensor) -> np.ndarray:
        """
        Maintain a sliding window of recent action chunks and compute a
        weighted average of the predictions for the *current* timestep.

        new_chunk: shape [chunk_size, action_dim]
        Returns:   shape [action_dim]
        """
        self._chunk_queue.append(new_chunk)

        # For each chunk in the window, the action relevant to *now* is
        # chunk[offset] where offset is how many steps ago it was predicted.
        weighted_sum = None
        total_weight = 0.0

        for k, chunk in enumerate(reversed(self._chunk_queue)):
            offset = k  # 0 = just predicted, k = predicted k steps ago
            if offset >= chunk.shape[0]:
                continue  # this chunk no longer covers the current step
            w = np.exp(-ENSEMBLE_DECAY * k)
            action = chunk[offset].cpu().numpy()
            weighted_sum = action * w if weighted_sum is None else weighted_sum + action * w
            total_weight += w

        return weighted_sum / total_weight

    # ---------------------------------------------------------------------------
    # F/T termination check
    # ---------------------------------------------------------------------------
    def _check_insertion_complete(self, obs_msg: Observation, elapsed: float) -> bool:
        if elapsed < MIN_INSERTION_TIME_SEC:
            return False
        try:
            fz = obs_msg.controller_state.tcp_wrench.force.z
        except AttributeError:
            return False  # F/T not available in this build

        if not hasattr(self, "_peak_fz"):
            self._peak_fz = 0.0

        self._peak_fz = max(self._peak_fz, abs(fz))

        # Successful insertion: force spiked past threshold then dropped
        if self._peak_fz > INSERTION_FORCE_THRESHOLD_N and abs(fz) < INSERTION_FORCE_DROP_N:
            self.get_logger().info(
                f"Insertion complete (F/T): peak={self._peak_fz:.2f}N, now={fz:.2f}N"
            )
            return True
        return False

    # ---------------------------------------------------------------------------
    # Motion command builder
    # ---------------------------------------------------------------------------
    def _make_motion_update(self, action: np.ndarray) -> MotionUpdate:
        twist = Twist(
            linear=Vector3(x=float(action[0]), y=float(action[1]), z=float(action[2])),
            angular=Vector3(x=float(action[3]), y=float(action[4]), z=float(action[5])),
        )
        msg = MotionUpdate()
        msg.velocity = twist
        msg.header.frame_id = "base_link"
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.target_stiffness = np.diag([100., 100., 100., 50., 50., 50.]).flatten()
        msg.target_damping   = np.diag([ 40.,  40.,  40., 15., 15., 15.]).flatten()
        msg.feedforward_wrench_at_tip = Wrench(
            force=Vector3(x=0., y=0., z=0.),
            torque=Vector3(x=0., y=0., z=0.),
        )
        msg.wrench_feedback_gains_at_tip = [0.5, 0.5, 0.5, 0.0, 0.0, 0.0]
        msg.trajectory_generation_mode.mode = TrajectoryGenerationMode.MODE_VELOCITY
        return msg

    # ---------------------------------------------------------------------------
    # Main entry point
    # ---------------------------------------------------------------------------
    def insert_cable(
        self,
        task: Task,
        get_observation: GetObservationCallback,
        move_robot: MoveRobotCallback,
        send_feedback: SendFeedbackCallback,
        **kwargs,
    ) -> bool:
        self.model.reset()
        self._chunk_queue = collections.deque(maxlen=ENSEMBLE_WINDOW)
        self._peak_fz = 0.0
        self._ema_action = None

        self.get_logger().info(f"DylACTPolicy.insert_cable() | task={task}")
        start_time = time.time()
        step = 0
        period = 1.0 / CONTROL_HZ

        while True:
            loop_start = time.time()
            elapsed = loop_start - start_time

            if elapsed > MAX_DURATION_SEC:
                self.get_logger().warn("Timeout reached — exiting.")
                return False

            # --- Observation ---
            obs_msg = get_observation()
            if obs_msg is None:
                self.get_logger().warn("No observation — skipping step.")
                time.sleep(period)
                continue

            # --- Inference ---
            obs_tensors = self._build_obs(obs_msg)
            with torch.inference_mode():
                norm_chunk = self.model.select_action(obs_tensors)
                # norm_chunk may be [action_dim] or [chunk_size, action_dim]
                # ACT's select_action() returns one action per call (internally queues chunk)
                # We replicate the chunk buffer ourselves for ensembling.
                # Wrap single action as a 1-step chunk for the ensemble queue.
                if norm_chunk.dim() == 1:
                    norm_chunk = norm_chunk.unsqueeze(0)

            # Un-normalise
            raw_chunk = (norm_chunk * self.action_std) + self.action_mean  # [N, action_dim]

            # --- Temporal ensembling ---
            action = self._ensemble_action(raw_chunk)

            # --- EMA smoothing ---
            if self._ema_action is None:
                self._ema_action = action
            else:
                self._ema_action = EMA_ALPHA * self._ema_action + (1.0 - EMA_ALPHA) * action
            action = self._ema_action

            # --- Send command ---
            move_robot(motion_update=self._make_motion_update(action))
            send_feedback(f"step={step} elapsed={elapsed:.1f}s")

            # --- F/T early exit ---
            if self._check_insertion_complete(obs_msg, elapsed):
                return True

            step += 1
            elapsed_loop = time.time() - loop_start
            time.sleep(max(0.0, period - elapsed_loop))
