# cheat code to test the policy node 

#first change to the aic directory

cd ~/ai_challenge_ws/ai_industry_challenge_deep_dive/ws_aic/src/aic

# then run the pixi environment command
# to test the policy
pixi run ros2 run aic_model aic_model --ros-args -p use_sim_time:=true -p policy:=aic_example_policies.ros.CheatCode