# this is to test the policy node created by
# intrinsic ai for the wave arm policy

#first change to the aic directory

cd ~/ai_challenge_ws/ai_industry_challenge_deep_dive/ws_aic/src/aic

# run the pixi environment command
# run the following command:
pixi run ros2 run aic_model aic_model --ros-args -p use_sim_time:=true -p policy:=aic_example_policies.ros.WaveArm