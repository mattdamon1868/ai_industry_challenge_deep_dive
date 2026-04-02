# Mujoco Simulation Setup and Debugging

When going through this file use the [mujoco readme](https://github.com/intrinsic-dev/aic/blob/main/aic_utils/aic_mujoco/README.md) from intrinsic to reference steps discussed through this documentation.

> *NOTE:* Before we continue lets install pip in the container which will be useful for installing other packages

```bash
# indicate distrobox to use Docker as the container manager
user@host:~$ export DBX_CONTAINER_MANAGER=docker
# enter the container
user@host:~$ distrobox enter -r aic_eval
 
# lets get pip installed useful for later
user@aic_eval:~$ sudo apt install python3-pip
# get toml as well
user@aic_eval:~$ pip3 install toml
# OR
user@aic_eval:~$ sudo apt install python3-toml
```

## Scene Generation Debug
The scene generation workflow discusses how to launch aic_bringup directly from the using ros2 launch as opposed to using the /entrypoint.sh container environment setup. 
The launch file they want us to run generates an environment file *aic.sdf* which can be exported to a mujoco file or mjcf file. When you attempt to run the ros2 launch file you will notice that it won't work that because you need to build the environment using *colcon build*.

> *NOTE:* Need to be running the aic container in order for this to work

1. Build the packages
You will need to build all the required packages first try building the aic_bringup package and see what is missing you might get a message that gives you the following output:

  Check that the following packages have been built:
  - aic_assets
  - control_msgs
  - controller_manager_msgs
  - joint_state_publisher
  - ros2_control_test_assets
  - ros_gz_interfaces
  - aic_scoring
  - joint_limits
  - joint_state_publisher_gui
  - kinematics_interface
  - aic_engine
  - gz_plugin_vendor
  - hardware_interface
  - kinematics_interface_kdl
  - ur_description
  - controller_interface
  - gz_common_vendor
  - gz_msgs_vendor
  - hardware_interface_testing
  - aic_controller
  - controller_manager
  - gz_fuel_tools_vendor
  - gz_physics_vendor
  - gz_rendering_vendor
  - gz_transport_vendor
  - gz_gui_vendor
  - gz_sensors_vendor
  - ros_gz_bridge
  - gz_sim_vendor
  - aic_gazebo
  - ros_gz_sim
  - aic_description

All these packages need to be installed therefore start going one by one

```bash
user@aic_eval:~$colcon build --packages-select <package_name>
```

If you run into issues with any of the packages not building properly it is likely due to another package requirement for the one you are installing for example with *aic_gazebo* you need these packages:

  - gz_plugin_vendor
  - gz_common_vendor
  - gz_msgs_vendor
  - gz_fuel_tools_vendor
  - gz_physics_vendor
  - gz_rendering_vendor
  - gz_transport_vendor
  - gz_gui_vendor
  - gz_sensors_vendor
  - gz_sim_vendor

You can either install each of them individully as before **OR** you can use the `--packages-up-to` command in `colcon build` which will install all the required packages up to the package selected (`<package_name>`).

```bash
# this command ensures that all the packages required for the package you name get installed properly
user@aic_eval:~$ colcon build \
            --packages-up-to <package_name> \
            --cmake-args -DCMAKE_BUILD_TYPE=Release
```

Continue to do this until there are no more errors when running `colcon build --packages-select aic_bringup`

> *NOTE:* When building the `aic_interfaces` package make sure to select the interfaces that are inside the package, `aic_control_interfaces` etc. 

2. Convert the SDF to MJCF
> *Note:* Step 3 in the scene generation section

Converting the sdf to an mjcf file, which is a file that mujoco can interpret to run the mujoco environment.

```bash
# use the sdf2mjcf cli tool to convert the fixed /tmp/aic.sdf to mjcf format
user@aic_eval:~$ source /opt/ros/kilted/setup.bash
# source install
user@aic_eval:~$ source install/setup.bash
user@aic_eval:~$ cd ~/ai_challenge_ws/ai_industry_challenge_deep_dive/ws_aic
# make a new directory
user@aic_eval:~$ mkdir -p ~/ai_challenge_ws/ai_industry_challenge_deep_dive/aic_mujoco_world
# make sure the sdformat_mjcf is installed
user@aic_eval:~$ colcon build --packages-select sdformat_mjcf
user@aic_eval:~$ export PYTHONPATH=/usr/lib/python3/dist-packages:$PYTHONPATH
user@aic_eval:~$ export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
user@aic_eval:~$ sdf2mjcf /tmp/aic.sdf ~/ai_challenge_ws/ai_industry_challenge_deep_dive/aic_mujoco_world/aic_world.xml
# OR run this in case the above command doesn't work
# list accesses the exact file location of sdf2mjcf 
user@aic_eval:~$ python3 /home/dylan/ai_challenge_ws/ai_industry_challenge_deep_dive/ws_aic/install/sdformat_mjcf/bin/sdf2mjcf \
  /tmp/aic.sdf \
  ~/ai_challenge_ws/ai_industry_challenge_deep_dive/aic_mujoco_world/aic_world.xml
```

You will most likely run into an issue here because yet again there are some extra packages that need to be installed for the container `dm_control` and `pycollada` (which are required by the sdformat_mjcf) 

```bash
# we need to use the --break-system-packages inorder to force the install which is accetable since its inside the container
user@aic_eval:~$ pip3 install dm_control --break-system-packages
user@aic_eval:~$ pip3 install pycollada "trimesh[easy]" --break-system-packages

# Rerun the command from above
user@aic_eval:~$ sdf2mjcf /tmp/aic.sdf ~/ai_challenge_ws/ai_industry_challenge_deep_dive/aic_mujoco_world/aic_world.xml
# OR run this in case the above command doesn't work
# list accesses the exact file location of sdf2mjcf 
user@aic_eval:~$ python3 /home/dylan/ai_challenge_ws/ai_industry_challenge_deep_dive/ws_aic/install/sdformat_mjcf/bin/sdf2mjcf \
  /tmp/aic.sdf \
  ~/ai_challenge_ws/ai_industry_challenge_deep_dive/aic_mujoco_world/aic_world.xml
```

It should transfer the `aic.sdf` to an mjcf file which will be locatedin the aic_mujoco_world directory as specified.
While also generating new files in order which will be used to run the mujoco simulation.

3. Organize MJCF files

> *NOTE:* This is step 4 in the scene generation workflow

```bash
# always copy or symlink the generated mesh assets from the ~/aic_mujoco_world so mujoco can find the files
user@aic_eval:~$ cp -r ~/ai_challenge_ws/ai_industry_challenge_deep_dive/aic_mujoco_world/* ~/ai_challenge_ws/ai_industry_challenge_deep_dive/ws_aic/src/aic/aic_utils/aic_mujoco/mjcf/
# build the mujoco environment need to be in the aic eval container for this
user@aic_eval:~$ colcon build --packages-seleect aic_mujoco
```

4. Generate the final MJCF files and View in Mujoco
> *NOTE:* This is step 5/6 in the scene generation workflow

```bash
# open a new terminal ctrl+alt+t
user@host:~$ cd ~/ai_challenge_ws/ai_industry_challenge_deep_dive/ws_aic/src/aic
# open pixi shell
user@host:~$ pixi shell

# run this commands in the pixi shell which will activate the environment as needed
(aic) user@host:~$ python3 scripts/add_cable_plugin.py --input mjcf/aic_world.xml --output mjcf/aic_world.xml --robot_output mjcf/aic_robot.xml --scene_output mjcf/scene.xml
# change to the proper directory
(aic) user@host:~$ cd ~/ai_challenge_ws/ai_industry_challenge_deep_dive/ws_aic

```

## Mujoco w/ ROS2 Control

1. Install Dependencies
*Step 1 in mujoco doc Part 2*

When installing the dependencies I got a `404 Not Found` error output therefore I had to force the system to install and fix the missing packages without exiting. 

```bash
# 404 error
404  Not Found [IP: 2600:3402:200:227::2 80]
E: Failed to fetch http://packages.ros.org/ros2/ubuntu/pool/main/r/ros-kilted-ament-mypy/ros-kilted-ament-mypy_0.19.2-2noble.20260115.032537_amd64.deb  404  Not Found [IP: 2600:3402:200:227::2 80]
# the sudo apt-get install -f -y command helps with fixing missing packages and resolves it without exiting the rosdep install 
user@aic_eval:~$ rosdep install --from-paths src --ignore-src --rosdistro kilted -yr \
  --skip-keys "gz-cmake3 DART libogre-dev libogre-next-2.3-dev ros-kilted-ament-cmake-clang-format ros-kilted-ament-mypy" \
  --reinstall 2>/dev/null; sudo apt-get install -f -y
```

2. Build the Workspace
I got an error that looked like:
```bash
Summary: 0 packages finished [1.32s]
  1 package failed: aic_control_interfaces
  7 packages aborted: aic_task_interfaces control_msgs controller_manager_msgs gz-cmake4 realtime_tools ros2_control_test_assets ros_gz_interfaces
  5 packages had stderr output: aic_control_interfaces aic_task_interfaces control_msgs controller_manager_msgs ros_gz_interfaces
  105 packages not processed
```
which has to do with the previous `build/` directory we did therefore lets remove it before re-building the workspace.

```bash
# a symlink error
--- stderr: aic_control_interfaces                                 
failed to create symbolic link '/home/dylan/ai_challenge_ws/ai_industry_challenge_deep_dive/ws_aic/build/aic_control_interfaces/ament_cmake_python/aic_control_interfaces/aic_control_interfaces' because existing path cannot be removed: Is a directory
gmake[2]: *** [CMakeFiles/ament_cmake_python_symlink_aic_control_interfaces.dir/build.make:70: CMakeFiles/ament_cmake_python_symlink_aic_control_interfaces] Error 1
gmake[1]: *** [CMakeFiles/Makefile2:452: CMakeFiles/ament_cmake_python_symlink_aic_control_interfaces.dir/all] Error 2
gmake[1]: *** Waiting for unfinished jobs....
gmake: *** [Makefile:146: all] Error 2
---
```

I also got an symlink error which can be avoided by simply removing the notation `--symlink-install` and while were at it remove `--merge-install` this might also cause an issue. Now re-run the build command and confirm it builds properly.

```bash
# remove the build package
user@aic_eval:~$ rm -rf build/
# rebuild the workspace with this updated command line
user@aic_eval:~$ GZ_BUILD_FROM_SOURCE=1 colcon build \
  --cmake-args -DCMAKE_BUILD_TYPE=Release \
  --packages-ignore lerobot_robot_aic
```
> *NOTE:* These were the errors that I got when building the workspace with mujoco so if you have a different error please make sure to add it to this docu



## Launching Mujoco with ros2_control
I ran into an issue where the simulation would not run and this was due to the system running out of shared memory. Specifically the shared memory is failing with the `ZENOH_CONFIG_OVERRIDE` because there isn't enough `/dev/shm` space.
We can fix this by simply changing the export command from *true* to *false*:
> *NOTE:* This might decrease performance but will avoid the error.

```bash
# in terminal 2 inside the docker container
user@aic_eval:~$ source ~/ai_challenge_ws/ai_industry_challenge_deep_dive/ws_aic/install/setup.bash
user@aic_eval:~$ export RMW_IMPLEMENTATION=rmw_zenoh_cpp
# changing the enabled from 'true' to 'false'
user@aic_eval:~$ export ZENOH_CONFIG_OVERRIDE='transport/shared_memory/enabled=false'
user@aic_eval:~$ ros2 run rmw_zenoh_cpp rmw_zenohd
```

Once this is done you can run teleoperations and move onto the example policies section.

*Last update on 04.01.2026*