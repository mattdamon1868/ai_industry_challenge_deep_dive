# AI for Industry Challenge — Weekly Gameplan


**Team:** Deep Dive 
**Challenge Period:** March 2 – ~July 31, 2026  
**Registration Deadline:** April 17, 2026  
**Toolkit Repo:** [intrinsic-dev/aic](https://github.com/intrinsic-dev/aic)
**Qualification (Mar 2 - May 15):** Participants train and test their cable assembly models in simulation. Evaluation Period: May 18 - 27. Top 30 announced May 28.
**Phase 1 (May 28 - Jul 14):** Qualified teams advance and gain access to Intrinsic Flowstate to develop a complete cable handling solution. Evaluation Period: Jul 14 - 21. Top 10 announced Jul 22.
**Phase 2 (Jul 27 - Aug 25):** Top teams move on to deploy and refine their solutions on a physical workcell provided by Intrinsic for real-world testing and evaluation. Evaluation Period: Aug 26 - Sep 4. Winner announced Sep 8.

---

## How to Use This Document

Each week has a **goal**, **assigned tasks**, a **deliverable** that proves the week was successful, and **resources** to reference. Tasks are labeled by role where relevant — adapt to your team size.

The qualification phase deadline has not been announced yet (TBA on challenge site). This plan assumes roughly 6–8 weeks for qualification, which could shift. Adjust accordingly when the deadline is posted.

---

## 1: Setup (Weeks 1–2)

### Week 1 — March 2–8: Environment Setup & Toolkit Familiarization

**Goal:** Every team member can run the AIC evaluation environment locally and understands the submission interface.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Attend kick-off webinar (Mar 3, 9am PT) | All |  |
| 2 | Clone `intrinsic-dev/aic` repo, read all docs in `docs/` | All |  |
| 3 | Follow `docs/getting_started.md` — install Docker, Distrobox, Pixi, build evaluation container | All |  |
| 4 | Run `aic_engine` with `sample_config` — confirm Gazebo sim launches, robot moves, cameras stream | All |  |
| 5 | Study `aic_interfaces` — map out all available ROS 2 topics, services, actions | All |  |
| 6 | Study `aic_controller` — understand how motion commands reach the robot, force limits | All |  |
| 7 | Run example policies from `aic_example_policies/` — observe behavior, read the code | All |  |
| 8 | Study `docs/scoring.md` and `docs/scoring_tests.md` — run scoring test examples locally | All |  |
| 9 | Study `docs/challenge_rules.md` — understand behavioral requirements for `aic_model` | All |  |
| 10 | Read `docs/scene_description.md` and `docs/task_board_description.md` — understand the physical setup | All |  |

**Deliverable:** Every team member can run `aic_engine`, see the robot in Gazebo, and has read all documentation. Share screenshots in team chat.

**Key docs to read this week:**
- `docs/getting_started.md`
- `docs/overview.md`
- `docs/scoring.md`
- `docs/challenge_rules.md`
- `docs/aic_interfaces.md`
- `docs/aic_controller.md`
- `docs/scene_description.md`
- `docs/task_board_description.md`
- `docs/policy.md`

---

### Week 2 — March 9–15: First Policy Submission & Pipeline Validation

**Goal:** Submit a trivial policy through the full pipeline to validate the end-to-end submission workflow. Score doesn't matter — proving the pipeline works is what matters.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Follow `docs/policy.md` tutorial — create a new policy node from the `aic_model` template | Lead |  |
| 2 | Write a hardcoded "move to fixed pose" policy — just to confirm commands reach the robot | Lead |  |
| 3 | Run it locally against `aic_engine` — confirm scoring output appears | Lead |  |
| 4 | Package the policy into a Docker container per `docs/submission.md` | Lead |  |
| 5 | Verify container locally per `docs/submission.md#verify-locally` | Lead |  |
| 6 | Submit to the official portal using auth token — confirm submission is accepted | Lead |  |
| 7 | Set up team's private GitHub repo with our project structure | Lead | |
| 8 | Begin mapping the observation space: record all ROS topics, message types, frame rates, coordinate frames | Perception |  |
| 9 | Extract URDF/SDF from `aic_description/` — study robot kinematics, joint limits, TCP frame | Controls |  |
| 10 | Inventory 3D assets in `aic_assets/` — cable models, connector models, task board | Sim |  |

**Deliverable:** A submission appears on the leaderboard (even with a near-zero score). Team repo is set up on GitHub.

---

## 2: Baseline Development (Weeks 3–5)

### Week 3 — March 16–22: Observation Pipeline & Baseline Controller

**Goal:** Build a working observation pipeline and a simple rule-based insertion policy that can score points.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Build observation preprocessor: subscribe to all 3 camera topics, joint states, F/T wrench — log data to HDF5 | Perception |  |
| 2 | Visualize camera feeds — understand what the wrist cameras see at different robot poses | Perception |  |
| 3 | Write a scripted policy: approach → contact detection → push along Z — aim for at least one partial insertion | Controls |  |
| 4 | Implement force-based contact detection using F/T topic (threshold on Z-force) | Controls |  |
| 5 | Study `aic_controller` force limiting behavior — understand what happens when you exceed force limits | Controls |  |
| 6 | Set up MuJoCo training environment with UR5e + cable (separate from AIC toolkit, for policy training) | Sim |  |
| 7 | Port URDF from `aic_description/` into MuJoCo format (or use MuJoCo Menagerie UR5e) | Sim |  |
| 8 | Run scoring tests from `docs/scoring_tests.md` against the scripted policy | All |  |
| 9 | Submit scripted policy — aim for a non-zero score on at least one trial | Lead |  |

**Deliverable:** A scripted policy that detects contact and attempts insertion. Non-zero score on leaderboard.

---

### Week 4 — March 23–29: Data Collection & Teleoperation

**Goal:** Collect demonstration data for imitation learning. Get the training pipeline scaffolded.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Build teleoperation interface for the Gazebo sim (SpaceMouse or keyboard) | Sim |  |
| 2 | Collect 50+ demonstration trajectories of successful cable insertions via teleoperation | All |  |
| 3 | Record full observation + action pairs at 10 Hz: images, joint states, F/T, gripper, TCP pose | Sim |  |
| 4 | Build data loading pipeline (HDF5/Zarr → PyTorch DataLoader) | ML |  |
| 5 | Implement observation preprocessing module (image resize, normalization, proprio assembly) | ML |  |
| 6 | Set up Diffusion Policy training repo (clone `real-stanford/diffusion_policy`, adapt to our obs/action space) | ML |  |
| 7 | Improve scripted policy with spiral search for misaligned insertions | Controls |  |
| 8 | Create multiple `aic_engine` test configs with different cable/connector positions | All |  |
| 9 | Submit improved scripted policy — track score improvement | Lead |  |

**Deliverable:** 50+ recorded demonstrations. Diffusion Policy training code adapted to our observation/action space. Improved scripted policy score.

---

### Week 5 — March 30 – April 5: First Learned Policy

**Goal:** Train and evaluate the first learned policy. It doesn't need to beat the scripted baseline yet — proving the training pipeline works is the priority.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Train Diffusion Policy on collected demonstrations (start with small model, ~50 demos) | ML |  |
| 2 | Evaluate learned policy in Gazebo via `aic_engine` — compare to scripted baseline | ML |  |
| 3 | Implement action space: decide if policy outputs TCP deltas, joint targets, or full hybrid (pose + wrench + stiffness) | ML + Controls |  |
| 4 | Set up WandB/Tensorboard logging for training runs | ML |  |
| 5 | If using MuJoCo for training: validate sim-to-sim transfer to Gazebo (same policy, different sim) | Sim |  |
| 6 | Implement ONNX export pipeline (PyTorch → ONNX → inference in container) | ML |  |
| 7 | Profile inference latency — ensure policy runs within 10 Hz budget inside Docker container | ML |  |
| 8 | Collect 50 more demonstrations with harder configurations (more misalignment, different cables) | All |  |
| 9 | Submit best policy (scripted or learned, whichever scores higher) | Lead |  |

**Deliverable:** A trained policy checkpoint. ONNX export working. Training metrics logged. Comparison of learned vs. scripted scores.

---

## 3: Optimization (Weeks 6–8)

### Week 6 — April 6–12: Policy Improvement & Generalization

**Goal:** Improve policy success rate across different cable/connector configurations. Begin variable-admittance integration if using hybrid approach.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Analyze failure modes: where does the policy fail? (approach? grasp? alignment? insertion?) | All |  |
| 2 | Collect targeted demonstrations for failure cases | All |  |
| 3 | Retrain with expanded dataset (100+ demos) | ML |  |
| 4 | Implement domain randomization if training in MuJoCo (cable stiffness, lighting, positions) | Sim |  |
| 5 | If using hybrid approach: integrate variable-admittance output heads into policy action space | Controls + ML |  |
| 6 | Evaluate generalization: test across all cable types and connector positions in `aic_engine` configs | All |  |
| 7 | Optimize Docker container size and startup time | Lead |  |
| 8 | Submit improved policy — aim for top 30 | Lead | |

**Deliverable:** Policy with measurably improved success rate. Failure analysis document. Submission aiming for top 30.

---

### Week 7 — April 13–19: Score Optimization & Deadline Prep

**Goal:** Maximize qualification score. Registration deadline is April 17 — ensure all team members are registered.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | **DEADLINE: April 17 — all team members must be registered** | Lead |  |
| 2 | Optimize cycle time (efficiency scoring component) | Controls |  |
| 3 | Tune force limits to minimize safety penalties | Controls |  |
| 4 | Tune insertion precision (precision scoring component) | ML + Controls |  |
| 5 | Ensemble or fallback strategy: if learned policy fails, fall back to scripted baseline | Lead | |
| 6 | Run full scoring suite from `docs/scoring_tests.md` — identify weakest scoring area | All |  |
| 7 | Stress test: run 50+ trials across randomized configs, measure success rate | All |  |
| 8 | Submit best-performing policy | Lead |  |

**Deliverable:** Highest achievable qualification score submitted. All team members registered.

---

### Week 8 — April 20–26: Buffer Week / Continued Optimization

**Goal:** Continue improving if qualification deadline hasn't passed. Polish submission.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Investigate FAST tokenization for inference speedup (if latency is a bottleneck) | ML | |
| 2 | Experiment with action chunking horizon length | ML | ☐ |
| 3 | Add recovery behaviors: detect when insertion fails, retract, retry | Controls |  |
| 4 | Add more training data from edge cases | All |  |
| 5 | Final submission before qualification deadline | Lead |  |
| 6 | Begin preparing for Phase 1: read Intrinsic Flowstate SDK docs, plan IVM integration | Lead |  |

**Deliverable:** Final qualification submission. Prep notes for Phase 1.

---

## 4: If Selected for Phase 1 (Weeks 9–16, ~May–June)

### Weeks 9–10: Flowstate & IVM Integration

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Get access to Intrinsic Flowstate, install and set up | All |  |
| 2 | Study Intrinsic Vision Model (IVM) capabilities — pose detection, tracking, segmentation | Perception |  |
| 3 | Replace or augment camera-based perception with IVM outputs | Perception + ML |  |
| 4 | Integrate `intrinsic-ai/sdk` and `intrinsic-ai/sdk-ros` into our pipeline | Lead |  |
| 5 | Retrain policy with IVM features as additional observation inputs | ML |  |

### Weeks 11–14: Full Cable Handling Pipeline

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Extend from single insertion to full cable handling (grasp → route → insert) | All |  |
| 2 | Implement cable state estimation using IVM + cameras | Perception |  |
| 3 | Train multi-phase policy or state machine with phase-specific sub-policies | ML |  |
| 4 | Optimize for generalization across cable types and connector variants | ML + Sim |  |

### Weeks 15–16: Phase 1 Submission Polish

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Full system integration testing | All |  |
| 2 | Cycle time optimization | Controls |  |
| 3 | Final Phase 1 submission | Lead |  |

---

## 5: If Selected for Phase 2 (Weeks 17–20, ~June–July)

### Real Robot Deployment at Intrinsic HQ

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Remote access setup to physical workcell | Lead |  |
| 2 | Sim-to-real calibration: camera intrinsics, F/T sensor bias, gripper parameters | Controls | |
| 3 | Fine-tune admittance controller parameters on real hardware | Controls | |
| 4 | Collect real-world demonstrations if possible, fine-tune policy | ML |  |
| 5 | Iterative testing and refinement on physical workcell | All |  |
| 6 | Final submission | Lead |  |

---

## Weekly Rhythm

Every week follows this cadence:

| Day | Activity |
|-----|----------|
| **Monday** | Week kickoff: review this plan, assign/confirm task owners |
| **Tuesday–Thursday** | Heads-down development |
| **Friday** | Integration: merge branches, test end-to-end in `aic_engine` |
| **Saturday** | Submit best current policy to leaderboard |
| **Sunday** | Review scores, write brief retro (what worked, what didn't, plan adjustments) |

---

## Scoring Quick Reference

Keep these in mind every week every task should trace back to improving one of these:
For the detailed list of the scoring check out: https://github.com/intrinsic-dev/aic/blob/main/docs/scoring.md 
| Criterion | Weight | What Matters |
|-----------|--------|--------------|
| **Precision** | High | How close connectors are inserted to target position |
| **Safety** | High | Penalties for collisions and excessive force |
| **Efficiency** | Medium | Total cycle time for all insertion tasks |
| **Innovation** (Phase 2) | Bonus | Technical novelty, judged by expert panel |
| **Scalability** (Phase 2) | Bonus | Generalization potential across tasks |

---

## Key Links

| Resource | URL |
|----------|-----|
| AIC Toolkit | https://github.com/intrinsic-dev/aic |
| Challenge Page | https://www.intrinsic.ai/events/ai-for-industry-challenge |
| Challenge Rules | https://www.intrinsic.ai/ai-for-industry-challenge/rules |
| Community Forum | https://discourse.openrobotics.org/c/competitions/ai-for-industry-challenge/ |
| GitHub Issues | https://github.com/intrinsic-dev/aic/issues |
| Intrinsic SDK | https://github.com/intrinsic-ai/sdk |
| Diffusion Policy | https://github.com/real-stanford/diffusion_policy |
| FAST Tokenizer | https://arxiv.org/abs/2501.09747 |

---

*Last updated: March 6, 2026. Update this document weekly as deadlines are announced and priorities shift.*
