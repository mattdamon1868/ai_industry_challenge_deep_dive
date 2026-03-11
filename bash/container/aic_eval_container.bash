# Enter the eval container
# export the container manager to docker
export DBX_CONTAINER_MANAGER=docker

# enter the container
distrobox enter -r aic_eval

# launch the eval environment 
# change the ground truth to true if testing
# the cheat code policy
/entrypoint.sh ground_truth:=false start_aic_engine:=true