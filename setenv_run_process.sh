#!/usr/bin/env bash
echo "SENDER_EMAIL before export is: <$SENDER_EMAIL>"

export SENDER_PASSWORD="TODO: #FIXME"
export SENDER_EMAIL="FIXME: actual email"
echo "SENDER_EMAIL after export is: <$SENDER_EMAIL>"
export PATH="/home/ec2-user/.pyenv/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

# execute command and its parameters as input for this script
if [ $# -eq 0 ]; then
    echo "No command to execute"
else
    echo "Execute commands with its parameters: $@"
    eval $@
fi
