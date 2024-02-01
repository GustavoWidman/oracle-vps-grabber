# oracle-vps-grabber
This is a python script that uses the OCI library to try to get the free oracle ARM64 instance (with 4 cores and 24gb ram)


To deploy the app, copy the repo, edit the docker-compose.yaml file to include your OCI credentials and edit the oracle_key.pem file (inside the keys directory) to your oracle cloud private key.
There's optional fields for discord webhooks and discord user ids so you can get pinged whenever your vps is obtained.  

The restart option is off because the script exits when its done/catches a fatal exception.

After initial setup, a pair of private and public keys are generated and output to keys directory as vps_private_key.pem and vps_public_key.pub.
