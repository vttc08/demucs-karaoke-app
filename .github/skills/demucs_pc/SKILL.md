---
name: demucs_pc
description: Skills for controlling another computer running Demucs service, use when any changes are made to `demucs_svc/` folder
---

## Purpose
Start the service on another machine, check if it's reachable, and wake it up if necessary. This is essential for offloading Demucs processing to a dedicated machine while ensuring it's available when needed.

## Environments
Check the `.env` file located at the project root for the following variables:
- `MAC_ADDRESS`: The MAC address of the target machine (format `AA:BB:CC:DD:EE:FF`).
- `IP_ADDRESS`: The local IP address of the target machine for reachability checks.
- `WORKSPACE_FOLDER`: The shared workspace folder path on the target machine (e.g., `C:\Workspace`).
- `HOSTNAME`: The hostname of the target machine for SSH access (e.g., `demucs-pc`).

The remote machine is a Windows PC.

## Use this skill when
- Code change is requested in the `demucs_svc/` folder and need to be tested

## Procedure
1. Check whether the target machine is reachable by pinging its IP address.
```bash
ping -c 4 $IP_ADDRESS
```
2. If the machine is not reachable, send a Wake-on-LAN (WoL) magic packet to wake it up.
```bash
wakeonlan $MAC_ADDRESS
```
3. Wait for 10 seconds and check reachability again.
4. If it's reachable, proceed with SCP and copy the updated code in `demucs_svc/` to the target machine's workspace folder
```bash
scp -r demucs_svc/ $HOSTNAME:$WORKSPACE_FOLDER/demucs_svc
```
- the files are placed on the remote machine like `./demucs_svc/app.py` NOT `./demucs_svc/demucs_svc/app.py`
5. SSH into the target machine and run the code appropriately
- you should run the service in the background, bind on 0.0.0.0 with auto-reload for development
- run any nessecary tests or API calls to verify the changes over SSH (remote machine is Windows Powershell)

Note: if there are Python errors, you may need to activate the virtual environment and install dependencies on the target machine first using `pip`.