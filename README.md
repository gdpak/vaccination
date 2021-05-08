Crontab entry to run job every hour
'''
crontab entry

0 */1 * * * /home/ec2-user/set_env_process.sh python3 /home/ec2-user/vaccination/vaccine_avail.py

'''
