#!/bin/bash

HOST="https://api.woeden.com"

echo """
██     ██  ██████  ███████ ██████  ███████ ███    ██ 
██     ██ ██    ██ ██      ██   ██ ██      ████   ██ 
██  █  ██ ██    ██ █████   ██   ██ █████   ██ ██  ██ 
██ ███ ██ ██    ██ ██      ██   ██ ██      ██  ██ ██ 
 ███ ███   ██████  ███████ ██████  ███████ ██   ████ 
                                                                                                     
"""

echo "You are setting up a new robot. Please sign in."

echo -n "Email: "
read username
echo -n "Password: "
read -s password

echo

response=$(curl -s --location --request POST "$HOST/auth/login/" \
    --header 'Content-Type: application/json' \
    --data-raw "{
        \"username\": \"$username\",
        \"password\": \"$password\"
    }")
access=$(echo $response | grep -o '"access":"[^"]*' | grep -o '[^"]*$')
if [ $? -eq 0 ]; then
    echo
    echo "Awesome! You are now logged in."
else
    echo
    echo "Failed to log in. Please try again."
    exit 1
fi

echo -n "Please enter a name for the robot: "
read robot

response=$(curl -s --location --request POST "$HOST/robot/" \
    --header "Authorization: Bearer $access" \
    --header 'Content-Type: application/json' \
    --data-raw "{
        \"name\": \"$robot\"
    }")

robot_id=$(echo $response | grep -o '"id":[0-9]*' | grep -m 1 -o '[0-9]*$')
robot_password=$(echo "$response" | grep -o '"password":"[a-zA-Z0-9_-]*"' | grep -m 1 -o '[a-zA-Z0-9_-]*' | tail -1)

if [ $? -eq 0 ]; then
    mkdir -p $HOME/woeden
    echo "{ \"id\": $robot_id, \"password\": \"$robot_password\" }" > $HOME/woeden/config
    echo
    echo "Your new robot, $robot, is now registered in Woeden."
else
    echo
    echo "Failed to initialize your new robot. Please try again."
    exit 1
fi

echo "Please complete registration of the robot here: http://woeden.com/app/robot/$robot_id/settings/"

echo
echo "To use Woeden, please be sure to run our Docker container image. You can accomplish this by adding"
echo "the following service to the docker-compose file of your robotics project."

echo """
> woeden_monitor:
>     image: public.ecr.aws/woeden/agent
>     network_mode: host
>     restart: always
>     volumes:
>       - ~/woeden:/woeden
"""

echo "Alternatively, you can simply run the command below."

echo
echo "> docker run -d -v ~/woeden:/woeden --net host --restart always public.ecr.aws/woeden/agent:latest"
