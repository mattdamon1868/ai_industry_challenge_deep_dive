# Training Data

> **Why new data?** The new policy design uses force/torque (F/T) sensor readings, expanding the observation state from 26 dims to 32 dims. Existing recordings lack the F/T fields and cannot be used directly.

---

## Phase 1 — Data Collection

Each demonstration captures:
- 3 camera images per timestep
- 32-dim state vector (26 base + 6 F/T)
- 6-dim cartesian twist action

**Key difference from existing data:** `wrist_wrench` must be included in the observation at collection time.

### Step 1 — Patch the controller

Edit `get_observation()` in `aic_robot_aic_controller.py` to add the 6 F/T fields to `ObservationState`:

```bash
# Source file (edit this one)
~/ws_aic/src/aic/aic_utils/lerobot_robot_aic/lerobot_robot_aic/aic_robot_aic_controller.py

# Installed copy (verify the change took effect after pixi install)
.pixi/envs/default/lib/python3.12/site-packages/lerobot_robot_aic/aic_robot_aic_controller.py
```

### Step 2 — Record demonstrations

Run after the MuJoCo sim is up:

```bash
pixi run lerobot-record \
  --robot.type=aic_controller --robot.id=aic \
  --teleop.type=aic_keyboard_ee --teleop.id=aic \
  --robot.teleop_target_mode=cartesian --robot.teleop_frame_id=base_link \
  --dataset.repo_id=recordings/aic_ft_32dim \
  --dataset.single_task="insert cable into port" \
  --dataset.push_to_hub=false \
  --dataset.private=true \
  --play_sounds=false \
  --display_data=true
```

Target: **50–100 demonstrations** (via CheatCode policy or teleoperation).

Dataset saved to: `~/.cache/huggingface/lerobot/recordings/aic_ft_32dim`

---

## Phase 2 — Data Preparation

- Push recorded dataset to HuggingFace with the correct observation keys
- Verify each timestep has `observation.state` shape **(32,)** — not (26,)
- Normalization stats are computed automatically during training

---

## Phase 3 — Training Config

Update `config.json` to reflect the new state dimension:

```json
"input_shapes": {
  "observation.state": [32]  // was [26]
}
```

Then run `lerobot-train` with the updated config.
