# Troubleshooting

## Issues w/Launching the simulation

In order for the simulation to work as the aic repo intended we need to make sure that the local system is setup properly. When attempting to run the simulation you may run into some issues which can include missing nvidia drivers, not using the gpu for simulation which results in a slow sim time. 

### Missing Driver for GPU

If your simulation is running super slow it is probably using the CPU to run the simulation not the GPU. The GPU is needed in order to run this simulation at a faster rate (closer to real time). In order to use the GPU we need the proper nvidia-drivers for the gpu model. 

Check whether you have an nvidia-driver installed:

```
user@host:~$ dpkg -l | grep nvidia-driver
```

If you don't see anything then you need to install a driver for the GPU

Check what ubuntu drivers are available for your card

```
user@host:~$ ubuntu-drivers devices
```
This will list the drivers and make a recommendation, *however I personally wouldn't go with the recommendation instead select the most recent one, for me it was nvidia-driver-590*

Install the driver of choice

```
user@host:~$ sudo apt install nvidia-driver-590
# once installed reboot the system
user@host:~$ sudo reboot
```

> [!NOTE]
> If you get errors with installing the driver theres probably a conflict in packages so lets clean and retry
> ```
> # fix any broken packages
> $ sudo dpkg --configure -a
> $ sudo apt --fix-broken install
> 
> # remove any partial nvidia installs
> $ sudo apt remove --purge '*nvidia*'
> $ sudo apt autoremove
> $ sudo apt update
>
> # try again (input driver number with yours)
> $ sudo apt install nvidia-driver-<driver-number>
> ```

To confirm it is installed and working properly 

```
user@host:~$ nvidia-smi 

# OR

user@host:~$ glxinfo -B # needs the mesa-utils
                        # sudo apt install mesa-utils
```

If still not showing the graphics card

```
user@host:~$ sudo prime-select nvidia
```

> [!Important]
> When installing these drivers I am assuming that you are using Ubuntu 24.04 since the nvidia-driver-590 is for 24.04. If you have an older version then other issues such as kernel release version might be an issue.

### Secure boot is enabled

In order for the simulation to use the GPU Secure boot needs to be **disabled**, in order for the system to recognize the nvidia kernel.

> [!NOTE]
> This exists to prevent malicious code from running during the boot process. There is a way to add the GPU to the secure boot list however if this is being run on your personal computer its not a major issue if you disable it. 

*Check if the secure boot is on*
```
user@host:~$ mokutil --sb-state
```

If nothing is returned then you can need to disable to the **secure boot**

- Reboot and enter BIOS(press F2)
- Find **Secure Boot** under the Security/Boot tab
- Set to diabled
- Save and exit

Rerun the simulation

### Bashrc file interferring with `pixi`

Pixi creates its own environment but is based off the users local system therefore if you have a different version of ROS from **Kilted** then you will run into issues with the simulation. You will need to install that ROS_DISTRO please review the `getting_started.md` file to understand the required hardware and software for the project.

If you have **Kilted** and you attempt to run the policy seen in the `getting_started.md` or in [README.md](https://github.com/mattdamon1868/ai_industry_challenge_deep_dive/blob/main/README.md) and nothing happens in the simulation then the local `.bashrc` could be interferring with the `pixi` environment. Therefore check out your `.bashrc` and if there is anything related to ROS comment it out

```
# check whats in the file
user@host:~$ cat .bashrc

# similar to what you would see in your terminal
source /opt/ros/kilted/setup.bash
export ROS_DOMAIN_ID=0
export GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ros/kilted/lib:$ GZ_SIM_SYSTEM_PLUGIN_PATH
export LD_LIBRARY_PATH=/opt/ros/kilted/lib:$ LD_LIBRARY_PATH
export TURTLEBOT3_MODEL=burger

# if you see the ros related exports then comment them out

user@host:~$ nano .bashrc
#OR
user@host:~$

```

Rerun the policy with the simulation and your should see the 