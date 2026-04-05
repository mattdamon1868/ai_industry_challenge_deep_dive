# Git Commit Convention — Deep Dive

This document defines how we write commit messages on this project. Consistent commits make it easy to scan the git log, generate changelogs, and understand what changed without reading diffs.

---

## Format

Every commit message follows this structure:

```bash
<type>(<scope>): <short description>

<optional body>

<optional footer>
```

**Example:**

```bash
feat(policy): implement diffusion policy observation encoder

Adds ResNet-18 visual encoder with shared weights across 3 wrist cameras.
Proprioceptive encoder maps 31-dim state to 128-dim embedding.
Tested with random weights — forward pass produces correct output shapes.
```

---

## Types

Use one of these prefixes for every commit:

| Type | When to Use | Example |
|------|-------------|---------|
| `feat` | New feature or capability | `feat(control): add spiral search during insertion` |
| `fix` | Bug fix | `fix(policy): correct image normalization to [0,1]` |
| `docs` | Documentation changes only | `docs: update weekly gameplan with Phase 1 tasks` |
| `refactor` | Restructure code without changing behavior | `refactor(sim): extract domain randomization to config` |
| `test` | Adding or updating tests | `test(scoring): add local validation against aic_engine` |
| `chore` | Build, configs, dependencies, tooling | `chore(docker): add CUDA 12.1 to training image` |
| `perf` | Performance improvement | `perf(policy): switch to ONNX runtime, 40ms inference` |
| `ci` | CI/CD pipeline changes | `ci: add GitHub Actions build check on push` |
| `style` | Formatting, whitespace, linting (no logic) | `style(control): run black formatter on all Python files` |
| `data` | Training data, demo collection, datasets | `data: add 50 teleoperation demos for RJ45 connector` |

---

## Scopes

The scope tells your teammates which part of the project changed. Use one of these:

| Scope | Maps To | Description |
|-------|---------|-------------|
| `policy` | `src/policy/` | Diffusion policy, FAST tokenizer, observation preprocessing |
| `control` | `src/control/` | Admittance controller, safety monitor |
| `sim` | `src/sim/` | MuJoCo environment, domain randomization |
| `ros2` | `src/ros2_nodes/` | ROS 2 nodes for deployment |
| `docker` | `docker/` | Dockerfiles, container configs |
| `configs` | `configs/` | YAML configuration files |
| `scripts` | `scripts/` | Training, evaluation, export scripts |
| `aic` | `aic_model/` | Our policy implementation inside the AIC toolkit |
| *(omit)* | Multiple / top-level | Changes spanning multiple scopes or repo-level files |

---

## Rules

1. **Subject line under 72 characters.** GitHub truncates after this.

2. **Use imperative mood.** Write it as a command — "add feature" not "added feature" or "adding feature." A good test: your subject should complete the sentence *"If applied, this commit will ___."*

3. **No period at the end** of the subject line.

4. **Lowercase** the first word after the colon.

5. **Separate body from subject** with a blank line.

6. **Body explains why, not what.** The diff shows what changed. Use the body to explain the reasoning.

7. **One logical change per commit.** Don't mix a bug fix with a new feature. If you changed two things, make two commits.

---

## Examples

### Simple (no body needed)

```bash
fix(control): clamp admittance stiffness to safety bounds
```

```bash
docs: add git commit convention for the team
```

```bash
chore: update requirements.txt with mujoco 3.1
```

### With Body (explaining why)

```bash
fix(control): reduce max force threshold from 50N to 30N

The aic_controller applies scoring penalties above 25N based on
scoring_tests.md. Our previous 50N limit was causing safety score
deductions on every trial.
```

```bash
feat(policy): add force/torque history to observation space

Single-frame F/T readings are too noisy for reliable contact detection.
Adding a 10-step history buffer (1 second at 10Hz) lets the policy
detect force trends rather than reacting to individual spikes.
```

```bash
perf(policy): replace diffusion denoising with FAST token decoding

Diffusion inference was ~200ms (5Hz) which missed our 10Hz target.
FAST tokenization decodes in ~35ms, comfortably within budget.
Accuracy is within 2% of diffusion baseline on our eval suite.
```

### Breaking Change (footer)

```bash
refactor(aic): restructure policy interface to match aic_model v2

The aic_model template was updated upstream to use a new callback
signature. Our policy class now receives an ObservationBundle
dataclass instead of raw ROS messages.

BREAKING CHANGE: PolicyBase.step() signature changed.
All existing policy subclasses must be updated.
```

---

## Quick Reference Card

Copy this and keep it handy:

```bash
feat(scope): add new capability
fix(scope): fix a bug
docs: update documentation
refactor(scope): restructure without behavior change
test(scope): add or update tests
chore(scope): configs, deps, build tooling
perf(scope): make something faster
data: training data, demos, datasets

Scopes: policy | control | sim | ros2 | docker | configs | scripts | aic
```

---

## Git Tips

**Amend the last commit** (if you haven't pushed yet):
```bash
git commit --amend -m "fix(policy): correct message here"
```

**Write multi-line commits from the terminal:**
```bash
git commit -m "feat(control): add variable stiffness output" -m "Policy now outputs 6-dim stiffness vector per step.
Admittance controller reads these values at 500Hz."
```

**Check your recent commits:**
```bash
git log --oneline -10
```

Good log output should read like a changelog:
```
a3f1b2c feat(policy): add ONNX export for deployment container
9d2e4f1 fix(control): handle NaN in F/T readings gracefully
7c8a0d3 data: collect 25 demos for USB-C connector variant
4b1f6e9 refactor(sim): unify MuJoCo and Gazebo observation format
2e9c3a7 docs: update gameplan with Week 3 deliverables
f0d5b8e feat(aic): implement first learned policy in aic_model
```

---

## Merging a branch 
When pulling the main from the github repo
remember that it may give you some conflicting errors
```bash
# run this command when you are dealing with an merge error on the your local machine
user@host:~$ git fetch origin
# reset the origin
user@host:~$ git reset --hard origin/main

``` 

## Git push branch
You will need to make sure you have authentication access to the repo. You need to be a collaborator and accept the email request. Once that happens you need to get the git command that will give you the access token
```bash
user@host:~$ gh auth status
# it should return a failure since you don't have access yet
user@host:~$ gh auth login
# follow the steps to gain access and once complete try the status
# command again, and you should see that you have an access token, now you can push the branch to the repo and create a pull request. 
```

When pushing the branch make sure to commit with the same convention described in the earlier sections and then you need to push to the repository with this command:
```bash
# after creating a git commit, push it to the repo
user@host:~$ git push --set-upstream origin <branch_name>
```

If you want this to be done automatically without needing the `--set-upstream` command, you can edit the `git help config` script to enable automatic upstream tracking.

*Add this file to your repo at `CONTRIBUTING.md` or `docs/commit_convention.md` so it's always accessible.*
