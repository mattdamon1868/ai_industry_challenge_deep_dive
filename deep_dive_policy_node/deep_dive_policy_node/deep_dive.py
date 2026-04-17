'''
deep dive policy node

some ideas:

1.add force/torque feedback state 
the f/T sensor data is available in the observation message
cable insertion is a contact rich task 
force feedback is crucial more useful than the vision data feedback for this task

2. two phase policy:

2a. coarse approach: vision-guided get near the port  
2b. fine insertion(force guided compliance control)

could be two separate models or explicit switch between the modes
you could use the cheatcode policy as the exterior approach 
while focusing on the learning effort on the fine insertion policy

3. diffusion policy instead of the ACT policy 
lerobot supports this natively diffusion tends to outperform the ACT on contact-rich 
tasks because it handles multimodal action distributions better 

4. fix the image resolution 
image scaling is 0.25 which is pretty bad you're giving the model quarter-resolution images
to detect millimeter-scale alignment details even 0.5 would be better

5. increase the control frequency
4hz is too slow for precision insertion. bumping to 10hz-20hz gives the finer control
needed though you'd need to retrain to match

6. better data collection
architecture is designed for 10hz data collection architecture matters less than data 
quality use cheatcode policy to get the high quality demonstation collection via lerobot
record covering varied cable/port positions with domain randomization


DeepDive policy
Phase 1: approach (position control, cheatcode-style or vision)
    switch trigger: tcp within ~5mm of port (from task/ground truth)

phase 2: spiral search (reactive, no ML)
    small spiral velocity commands
    switch trigger: |F_z| > contact threshold AND lateral forces balanced

phase 3: fine insertion (ACT or diffusion, F/T augmented state)
    low Z stiffness, high lateral stiffness
    10hz control loop
    exit: F/T spike-then-drop (insertion complete)

    safety: max force watchdog stop if |F| > 20N
'''

import os

os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

import time
import json
import torch
import numpy as np
import cv2
import draccus
from pathlib import Path
from typing import Callable, Dict, Any, List
from rclpy.node import Node
from geometry_msgs.msg import Twist, Vector3

from aic_model.policy import (
    GetObservationCallback,
    MoveRobotCallback,
    Policy,
    SendFeedbackCallback,
)
from aic_control_interfaces.msg import (
    MotionUpdate,
    TrajectoryGenerationMode,
)
from geometry_msgs.msg import Wrench
from aic_model_interfaces.msg import Observation
from aic_task_interfaces.msg import Task
from aic_time_interfaces.msg import Timekeeper
from rclpy.duration import Duration
from lerobot.policies.act.modeling_act import ACTPolicy
from lerobot.policies.act.configuration_act import ACTConfig
from safetensors.torch import load_file
from huggingface_hub import snapshot_download


# --- F/T Sensor Normalisation ---
# Force: 0-80N -> [-1, 1]
# Torque: 0-15Nm -> [-1, 1]
FORCE_NORM_N = 50.0 # being conservative with the threshold
TORQUE_NORM_N_M = 5.0 # reasonable max for cable insertion

SAFETY_FORCE_THRESHOLD = 20.0 # Newtons

HF_REPO_ID = "grkw/aic_act_policy"   # swap for your fine-tuned checkpoint when ready
IMAGE_SCALE = 0.5                     # upgraded from 0.25 needs retraining to match

# constants for the spiral search
SPIRAL_RADIUS_GROWTH_RATE = 0.01 # m/s
SPIRAL_ANGULAR_RATE = 0.01 # rad/s
SPIRAL_Z_PRESSURE = 10.0 # N


class DeepDive(Policy):
    def __init__(self, parent_node: Node):
        super().__init__(parent_node)
        self.get_logger().info("DeepDive.__init__()")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.get_logger().info(f"Using device: {self.device}")
        
        # ---------------------------------------------------------------------------
        # Load model
        # ---------------------------------------------------------------------------
        # get the repository id from the parent node which loads the policy parameters
        repo_id = parent_node.declare_parameter("hf_repo_id", HF_REPO_ID).value
        self.get_logger().info(f"Downloading checkpoint: {repo_id}")
        policy_path = Path(
            snapshot_download(
                repo_id=repo_id,
                allow_patterns=["config.json", "*.safetensors"],
            )
        )
        # load the config.json file into a dictionary
        with open(policy_path / "config.json", "r") as f:
            config_dict = json.load(f)
            config_dict.pop("type", None)  # draccus doesn't know this field

        # parse config.json into an ACTConfig object
        config = draccus.decode(ACTConfig, config_dict)
        # get the chunk size from the config object
        self.chunk_size = config.chunk_size  # needed for ensembling
        # builds the model architechture from the config object
        self.model = ACTPolicy(config)
        # loads the model trained weights from the safetensors file
        self.model.load_state_dict(load_file(policy_path / "model.safetensors"))
        # sets the inference mode and moves it to the GPU if available
        self.model.eval().to(self.device)
        # 
        self.get_logger().info(f"Model loaded | chunk_size={self.chunk_size}")

        # ---------------------------------------------------------------------------
        # Load normalisation stats
        # ---------------------------------------------------------------------------
        # load the normalisation stats from the safetensors file
        stats = load_file(
            policy_path / "policy_preprocessor_step_3_normalizer_processor.safetensors"
        )

        def get_stat(key, shape):
            '''
            Get the statistics from the safetensors file from the snapshot_download

            slices and reshapes the tensor to the desired shape for each camera and the state vector

            '''
            return stats[key].to(self.device).view(*shape)
        
        self.img_stats = {
            camera: {
                "mean": get_stat(f"observation.images.{camera}_camera.mean", (1, 3, 1, 1)),
                "std": get_stat(f"observation.images.{camera}_camera.std", (1, 3, 1, 1)),
            }
            for camera in ("left", "center", "right")
        }
        self.state_mean = get_stat("observation.state.mean", (1, -1))
        self.state_std = get_stat("observation.state.std", (1, -1))
        self.action_mean = get_stat("action.mean", (1, -1))
        self.action_std = get_stat("action.std", (1, -1))
        self.start_time = 0.0
        self.polar_angle = 0.0
        self.get_logger().info("Normalisation stats loaded.")
    
        self.timekeeper_sub = self.create_subscription(
            Timekeeper, "/timekeeper", self._timekeeper_callback, 10
            )
    # ---------------------------------------------------------------------------
    # Force/Torque helper functions
    # ---------------------------------------------------------------------------

    def _timekeeper_callback(self, msg: Timekeeper) -> None:
        '''
        Start the timer for the spiral search
        '''
        self.start_time = msg.start_time()


    def _read_force_torque(self, obs_msg: Observation) -> np.ndarray:
        '''
        Read the wrench from the observation message to get force and torque

        observation message is from the aic_model_interfaces.msg import Observation
        wrench = array of 6 values: [fx, fy, fz, tx, ty, tz]

        returns force and torque states want them separate because they are different
        units and scales
        force = N
        torque = Nm
        '''
        wrench = obs_msg.wrist_wrench.wrench
        force_state = np.array([
            wrench.force.x,
            wrench.force.y,
            wrench.force.z,
        ], dtype=np.float32) # shape (3,) for force data type float32 because it's a 3D vector
        torque_state = np.array([
            wrench.torque.x,
            wrench.torque.y,
            wrench.torque.z,
        ], dtype=np.float32) # shape (3,) for torque data type float32 because it's a 3D vector
        return force_state, torque_state

    def _normalise_force_torque(self, force, torque):
        '''
        Normalise the force and torque to the range [-1, 1]
        '''
        force_norm = np.clip(force / FORCE_NORM_N, -1.0, 1.0) # clip(a{array}, a_min, a_max)
        torque_norm = np.clip(torque / TORQUE_NORM_N_M, -1.0, 1.0)
        return np.concatenate([force_norm, torque_norm]) # shape (6,) for force/torque data type float32 because it's a 6D vector

    def _build_obs_state_vector(self, obs_msg):
        '''
        Build the state vector for the policy

        tcp (tool center point)
        tcp_vel stands for (tool center point velocity)
        '''
        # process the tcp pose and velocity of the robot states
        # construct the flat state vector (26 dims) matching training order
        tcp_pose = obs_msg.controller_state.tcp_pose
        tcp_vel = obs_msg.controller_state.tcp_velocity

        base_state = np.array([
            # TCP Position (3)
            tcp_pose.position.x,
            tcp_pose.position.y,
            tcp_pose.position.z,
            # TCP Orientation (4) quaternion (x, y, z, w)
            tcp_pose.orientation.x,
            tcp_pose.orientation.y,
            tcp_pose.orientation.z,
            tcp_pose.orientation.w,
            # TCP Linear Velocity (3)
            tcp_vel.linear.x,
            tcp_vel.linear.y,
            tcp_vel.linear.z,
            # TCP Angular Velocity (3)
            tcp_vel.angular.x,
            tcp_vel.angular.y,
            tcp_vel.angular.z,
            # TCP Error (6)
            *obs_msg.controller_state.tcp_error,
            # Joint Positions (7)
            *obs_msg.joint_states.position[:7], # 7 joint positions (7-DOF arm)
        ], dtype=np.float32) # shape (26,) for base state data type float32

        # normalize the state vector
        raw_state_tensor = (
            torch.from_numpy(base_state).float().unsqueeze(0).to(self.device)
        )

        # process the force and torque sensor data
        # normalise the force and torque to the range [-1, 1]
        force_state, torque_state = self._read_force_torque(obs_msg)
        ft_norm = self._normalise_force_torque(force_state, torque_state)
        # return the concatenated state vector with the force/torque sensor data (32,) dimensions
        return np.concatenate([base_state, ft_norm])


    def _ensemble_action(self, new_chunk: torch.Tensor) -> np.ndarray:
        '''
        Maintain a sliding window of recent action chunks and compute a
        weighted average of the predictions for the *current* timestep.

        new_chunk: shape [chunk_size, action_dim]
        Returns:   shape [action_dim]
        '''
        pass

    def _check_insertion_complete(self, force: np.ndarray, elapsed: float) -> bool:
        '''
        Detect successful insertion using the F/T spike-then-drop signature.

        force: shape (3,) raw Newtons from _read_force_torque — NOT normalised.
               Raw values here so thresholds are physically meaningful
               (8N, 3N) rather than arbitrary normalised fractions.

        elapsed: seconds since insert_cable() started.

        self._peak_fz is reset to 0.0 in insert_cable() before the loop,
        so it accumulates the running maximum across loop iterations.
        '''
        # Ignore F/T for the first 2 seconds — the approach motion can
        # briefly press the cable against the surface before alignment,
        # causing a false-positive spike at the start.
        if elapsed < 2.0:
            return False

        fz = abs(force[2])  # Z-axis magnitude — the insertion direction

        # Track the highest Z-force seen so far this attempt
        self._peak_fz = max(self._peak_fz, fz)

        # Insertion complete when:
        # 1. Force spiked above 8N  (cable contacted the port rim)
        # 2. Force dropped below 3N (cable seated, resistance released)
        if self._peak_fz > 8.0 and fz < 3.0:
            self.get_logger().info(
                f'Insertion complete: peak={self._peak_fz:.2f}N, now={fz:.2f}N'
            )
            return True

        return False

    def _check_safety(self, force: np.ndarray) -> bool:
        '''
        Safety watchdog — call every loop iteration before sending any command.

        force: shape (3,): [Fx, Fy, Fz] raw Newtons from _read_force_torque.

        Returns True if safe to continue, False if any axis exceeds the limit.
        Caller should stop the policy and return False from insert_cable().

        np.any: stop if ANY single axis exceeds the threshold.
        np.all would require all three axes simultaneously — almost impossible.
        Only log on failure to avoid flooding the terminal at 10 Hz.
        '''
        if np.any(np.abs(force) > SAFETY_FORCE_THRESHOLD):
            self.get_logger().error(
                f'SAFETY: force exceeded {SAFETY_FORCE_THRESHOLD}N — '
                f'Fx={force[0]:.2f} Fy={force[1]:.2f} Fz={force[2]:.2f}'
            )
            return False
        return True

    @staticmethod
    def _img_to_tensor(
        raw_img,
        device: torch.device,
        scale: float,
        mean: torch.Tensor,
        std: torch.Tensor,
    ) -> torch.Tensor:
        '''
        Convert a ROS sensor_msgs/Image into a normalised tensor.

        raw_img : sensor_msgs/Image the ROS message (not a numpy array).
                  It carries .data (raw bytes), .height, and .width.

        device  : where to put the tensor (CPU or CUDA).

        scale   : resize factor IMAGE_SCALE (0.5) halves H and W.
                  Not a fixed output size because we don't know the camera
                  resolution until runtime. cv2.INTER_AREA is best for shrinking.

        mean/std: per-channel stats from the checkpoint, shape (1, 3, 1, 1).
                  The (1, 1) at the end lets PyTorch broadcast across H and W.

        Pipeline:
            bytes  →  numpy (height(H), width(W), 3)
                   →  resize
                   →  tensor (height(H), width(W), 3)
                   →  permute to (3, height(H), width(W))   [PyTorch is channels-first]
                   →  float, divide by 255   [uint8 → [0.0, 1.0]]
                   →  unsqueeze → (1, 3, height(H), width(W))  [add batch dim]
                   →  (t - mean) / std       [per-channel normalise]
        '''
        # Step 1: decode raw bytes into a numpy array shape (H, W, 3)
        img_np = np.frombuffer(raw_img.data, dtype=np.uint8).reshape(
            raw_img.height, raw_img.width, 3
        )

        # Step 2: resize using scale factor (not fixed pixels)
        # fx/fy are the scale factors for width/height
        if scale != 1.0:
            img_np = cv2.resize(
                img_np, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
            )

        # Step 3: numpy to tensor, then HWC(height,width,channels) to CHW, normalise to [0,1], add batch dim
        # .permute(2,0,1) is the PyTorch equivalent of numpy's .transpose(2,0,1)
        tensor = (
            torch.from_numpy(img_np)   # (H, W, 3) uint8
            .permute(2, 0, 1)          # (3, H, W)
            .float()                   # uint8 -> float32
            .div(255.0)                # [0, 255] -> [0.0, 1.0]
            .unsqueeze(0)              # (3, H, W) -> (1, 3, H, W)
            .to(device)
        )

        # Step 4: per-channel normalise using checkpoint stats
        # mean/std are (1, 3, 1, 1) broadcasts across height and width automatically
        return (tensor - mean) / std


    def _build_observation(self, obs_msg: Observation) -> Dict[str, torch.Tensor]:
        '''
        Build the observation tensor for the policy
        is the function that assembles everything the model needs to run inference
        output: is a state vector with 4 entries
        3 camera images: shape (1, 3, 224, 224)
        state vector: shape (1, 32) 
        {
            "observation.images.left_camera": tensor_shape(1, 3, 224, 224),
            "observation.images.right_camera": tensor_shape(1, 3, 224, 224),
            "observation.images.center_camera": tensor_shape(1, 3, 224, 224),
            "observation.state_vector": tensor_shape(1, 32),
        }
        the '1' is the batch size
        '''

        obs_images = {
            "observation.images.left_camera": self._img_to_tensor(
                obs_msg.left_image, 
                self.device,
                IMAGE_SCALE,
                self.img_stats["left"]["mean"],
                self.img_stats["left"]["std"]),
            "observation.images.right_camera": self._img_to_tensor(
                obs_msg.right_image,
                self.device,
                IMAGE_SCALE,
                self.img_stats["right"]["mean"],
                self.img_stats["right"]["std"]),
            "observation.images.center_camera": self._img_to_tensor(
                obs_msg.center_image,
                self.device,
                IMAGE_SCALE,
                self.img_stats["center"]["mean"],
                self.img_stats["center"]["std"]),
        }

        state_vector = self._build_obs_state_vector(obs_msg)

        # normalize the state vector
        raw_state_tensor = (
            torch.from_numpy(state_vector).float().unsqueeze(0).to(self.device)
        )
        obs_images["observation.state"] = (raw_state_tensor - self.state_mean) / self.state_std

        return obs_images

    def insert_cable(
        self,
        task: Task,
        get_observation: GetObservationCallback,
        move_robot: MoveRobotCallback,
        send_feedback: SendFeedbackCallback,
        **kwargs,
    ) -> bool:
        '''
        Insert the cable into the electrical port
        this will be called by the policy node

        '''
        self.model.reset()
        # reset the peak force_z to 0.0 so reset before the loop starts
        self._peak_fz = 0.0
        self.get_logger().info("DeepDive.insert_cable() starting...")

        start_time = time.time()
        delta_time = time.time() - start_time
        # run inference for 30 seconds
        while delta_time < 30.0:
            loop_start_time = time.time()
            
            # 1. Get & Process Observation
            observation_msg = get_observation()

            if observation_msg is None:
                self.get_logger().info("No observation received.")
                continue

            # 1a. if safety is violated, stop before doing anything else
            force, torque = self._read_force_torque(observation_msg)

            if not self._check_safety(force):
                self.get_logger().error("Safety violation detected. Stopping policy.")
                return False
            # 1b. check if insertion is complete
            elapsed = time.time() - start_time
            if self._check_insertion_complete(force, elapsed):
                self.get_logger().info("Insertion Completed")
                return True

            # 1c. build the observation tensor (expensive?)
            # 10 hz loop 100ms per loop GPU tensor operations: 1-2ms per camera image
            obs_tensors = self._build_observation(observation_msg)

            # 2. model inference
            with torch.inference_mode():
                # returns shape [1, 7] (first action of chunk)
                normalized_action = self.model.select_action(obs_tensors)

            # 3. Un-normalize Action
            # Formula: (norm * std) + mean
            raw_action_tensor = (normalized_action * self.action_std) + self.action_mean

            # 4. Extract and Command
            # raw_action_tensor is [1, 7], taking [0] gives vector of 7
            action = raw_action_tensor[0].cpu().numpy()

            
            # 5. Send twist command to the robot
            twist = Twist(
                linear=Vector3(
                    x = float(action[0]), y = float(action[1]), z = float(action[2])
                ),
                angular=Vector3(
                    x = float(action[3]), y = float(action[4]), z = float(action[5])
                ),
            )
            motion_update = self.set_cartesian_twist_target(twist)
            move_robot(motion_update = motion_update)
            send_feedback("in progress...")

            # Maintain control rate (approx 10hz loop = 0.1s sleep)
            elapsed = time.time() - loop_start_time
            time.sleep(max(0.0, 0.1 - elapsed))

        self.get_logger().info("Insertion failed, timeout reached.")
        return False
    
    def set_cartesian_twist_target(self, twist: Twist, frame_id: str = "base_link"):
        '''
        Set the cartesian twist target for the robot
        twist: (linear, angular) velocity commands
        '''
        # set the motion update message
        motion_update_msg = MotionUpdate()
        # set the velocity
        motion_update_msg.velocity = twist
        motion_update_msg.header.frame_id = frame_id
        # get timestamp from the clock
        motion_update_msg.header.stamp = self.get_clock().now().to_msg()
        # set the target stiffness and damping for the cartesian motion
        # and allows for variable impedance control
        motion_update_msg.target_stiffness = np.diag(
            [100.0, 100.0, 100.0, 50.0, 50.0, 50.0]
        ).flatten()
        motion_update_msg.target_damping = np.diag(
            [40.0, 40.0, 40.0, 15.0, 15.0, 15.0]
        ).flatten()
        # set the feedforward wrench at the tip which helps with stability and accuracy
        motion_update_msg.feedforward_wrench_at_tip = Wrench(
            force=Vector3(x=0.0, y=0.0, z=0.0),
            torque=Vector3(x=0.0, y=0.0, z=0.0),
        )
        # set the wrench feedback gains at the tip which helps with stability
        motion_update_msg.wrench_feedback_gains_at_tip = [0.5, 0.5, 0.5, 0.0, 0.0, 0.0]
        # set the trajectory generation mode which controls the motion planning 
        # and execution for the robot 
        motion_update_msg.trajectory_generation_mode.mode = (
            TrajectoryGenerationMode.MODE_VELOCITY
        )
        return motion_update_msg

    # spiral search for the port if misaligned
    def _spiral_search(
        self,
        get_observation: GetObservationCallback,
        move_robot: MoveRobotCallback,
        send_feedback: SendFeedbackCallback,
    ) -> bool:
        '''
        The ACT policy gets you close to the port but even a 1mm to 2mm misalignment means the
        cable will not fit through the port.
        Spiral search solves for the port if misaligned by executing a spiral pattern
        in the x-y plane while maintaining the z-axis force.
        Advantage it works in low light conditions too because it doesn't rely on vision
        '''
        # get the parameters angular_rate, z_pressure, and radius
        # calculate the radius growth of the spiral pattern
        # advance around a circle with a growing radius
        
        self.spiral_angle = 0.0
        spiral_start_time = self.start_time

        while True:
            loop_start_time = time.time()
            elapsed_time = loop_start_time - self.start_time
            
            if elapsed_time > SPIRAL_TIMEOUT_SEC:
                self.get_logger().error("Spiral search timeout reached.")
                return False
            
            obs_msg = get_observation()
            if obs_msg is None:
                self.get_logger().info("No observation received")
                continue

            force, _ = self._read_force_torque(obs_msg)

            if not self._check_safety(force):
                self.get_logger().error("Safety violation detected. Stopping spiral search.")
                return False

            #advance the spiral 
            delta_time = loop_start_time - spiral_start_time
            radius_growth_rate = SPIRAL_RADIUS_GROWTH_RATE * self.polar_angle
            self.polar_angle += SPIRAL_ANGULAR_RATE * delta_time
        
            if radius_growth_rate > SPIRAL_MAX_RADIUS:
                self.get_logger().info("Spiral search completed no port found.")
                return False

            vel_x = radius_growth_rate * np.cos(self.polar_angle)
            vel_y = radius_growth_rate * np.sin(self.polar_angle)
            z_pressure = SPIRAL_Z_PRESSURE

            if self._check_insertion_complete(force, delta_time):
                self.get_logger().info("Insertion completed during spiral search.")
                return True
            
            move_robot(
                motion_update = self.set_cartesian_twist_target(
                    Twist(
                        linear=Vector3(x=vel_x, y=vel_y, z=z_pressure),
                        angular=Vector3(x=0.0, y=0.0, z=0.0),
                    )
                )
            )
            send_feedback("spiral search in progress...")
            elapsed = time.time() - loop_start_time
            time.sleep(max(0.0, 0.1 - elapsed))
        self.get_logger().error("Spiral search failed, timeout reached.")
        return False

           
        
    # for the state_np array # exisiting 26 dimensions
    # add the F/T sensor data with the wrist_wrench force and torque
    # should add another 6 dimensions for total 32 dimensions
    def _add_ft_sensor_data(self, state_np: np.ndarray) -> np.ndarray:
        '''
        Add the F/T sensor data to the state_np array
        '''
        pass

    # for the action_np array # exisiting 31 dimensions
    # add the F/T sensor data with the wrist_wrench force and torque
    # should add another 6 dimensions for total 37 dimensions
    

    # fix the wrench field path
    # wrong fz = obs_msg.controller_state.tcp_wrench.force.z

    # correct fz = obs_msg.wrist_wrench.wrench.force.z


    