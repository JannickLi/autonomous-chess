# Aggregated agent deliberation results
# Published by Computer Agent after multi-agent deliberation

std_msgs/Header header
chess_msgs/AgentOpinion[] opinions
string selected_move_uci    # UCI notation of chosen move
string selected_move_san    # SAN notation of chosen move
float32 vote_confidence     # Overall confidence in selection (0.0-1.0)
string voting_summary       # Human-readable summary of voting process
