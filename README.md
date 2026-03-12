# Team Deep Dive: Robotics Industry Challenge


AI for Industry challenge targets a high-value bottleneck in modern manufacturing: electronics assembly. More specifically dexterous cable management and insertion, which today is a manual, repetitive process. This challenge will train an AI model using simulators and leveraging ROS communication for a manipulator to handle electronic assembly.

This is the repo for team deep dive. We are creating our own policy to work concurrently with the aic repo that will train the robot, executing
the motion planning to insert the cable for the electronic assembly

In order to run this simulation you will need to have the repo from Intrinsic AI, which can be found here:
`https://github.com/intrinsic-dev/aic/tree/main`

## Test Simulation Setup

One option is to run the bash scripts along with the aic repo:

1. Follow the intructions from the `docs/getting_started.md` file.

Proceed with one of these options once step 1 is completed

### Option 1: Run the bash script
1. To run the bash scripts use the README.md file [here](https://github.com/mattdamon1868/ai_industry_challenge_deep_dive/tree/main/bash/README.md)

### Option 2: Run in the terminal directly

1. Once the docker container has been created it can be accessed any time but first indicate distrobox to use(export) docker as the container manager for the distrobox. Execute in Terminal 1

```
user@host:~$ export DBX_CONTAINER_MANAGER=docker
```

2. Enter the eval container to test simulations

```
user@host:~$ distrobox enter -r aic_eval
```

3. Launch the evaluation environment in docker:

```
user@aic_eval:~$ /entrypoint.sh ground_truth:=false start_aic_engine:=true

```

4. In a second terminal run the pixi command needed run the ros environment dependencies with the policy created

```
user@host:~/ai_challenge_ws/ai_industry_challenge_deep_dive/ws_aic/src/aic$ pixi run ros2 run aic_model aic_model --ros-args -p use_sim_time:=true -p policy:=aic_example_policies.ros.WaveArm

```

`aic_example_policies.ros.WaveArm` should be exchanged with the name of the node <policy node created> as well as the policy name  <policy_name>

## Run Deep dive simulation

-upcoming

## Troublshooting

-upcoming