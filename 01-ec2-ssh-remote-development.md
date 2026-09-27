# Phase 1 — EC2 + SSH Remote Development Setup

## Phase Goal
Create a remote Linux development environment on AWS EC2 and connect to it securely from a MacBook using SSH and VS Code Remote SSH.

## Step 1: Launch EC2 instance
- Create an Ubuntu EC2 instance in AWS.
- Select the required instance size and storage.
- Review networking and security options before launch.

## Step 2: Configure security group
- Allow inbound SSH on port 22.
- Validate source IP access or use a learning-friendly rule.
- Confirm the instance is reachable from the local machine.

## Step 3: Connect using SSH
- Use the generated `.pem` file or a custom SSH key.
- Test connectivity from the terminal.
- Configure `~/.ssh/config` for easier access.

## Issues faced
- SSH connection timed out.
- EC2 public IP changed after stop/start.
- Duplicate SSH host entries caused confusion.
- VS Code Remote SSH disconnected intermittently.

## Root cause
- AWS Security Group rules were based on a previous laptop public IP.
- The EC2 instance was restarted and received a new public IPv4.
- Multiple SSH host aliases pointed to stale or conflicting values.
- Remote session reliability needed SSH keepalive tuning and resource updates.

## Fix
- Update the security group to allow SSH access for the current environment.
- Remove duplicate SSH config entries and keep one clean alias.
- Update the host IP in `~/.ssh/config`.
- Add keepalive settings and upgrade the instance if needed.
- Verify SSH service status and connectivity.

## What I learned
- EC2 public IPs are not always permanent.
- Security groups control access at the network layer.
- SSH configuration should be simple and centralized.
- VS Code Remote SSH is a practical way to work on cloud Linux machines.
- Keepalive settings improve session stability.

## Interview questions
1. Why did SSH fail even though the instance was running?
2. What is the purpose of a security group?
3. Why does an EC2 public IPv4 sometimes change?
4. What is the difference between a private and public SSH key?
5. How does VS Code Remote SSH improve remote development?

## Phase status ✅
Completed: EC2 instance created, SSH working, VS Code remote connection stable.
