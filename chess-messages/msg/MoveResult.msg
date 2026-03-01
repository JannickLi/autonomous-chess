# Result of move execution
# Published by robot control after completing (or failing) a move

std_msgs/Header header

# Echo back the move that was executed
string move_uci

# Success flag
bool success

# Error message if success=false
string error

# Time taken to execute the move in seconds
float32 execution_time_sec
