#!/usr/bin/env bash

  # bootstrap.sh — Install all host-level prerequisites for the devops-homelab project.

  set -euo pipefail
                                                                                                                                     
  # --------------------------------------------------------------------------                                                       
  # Helpers
  # --------------------------------------------------------------------------                                                       
                                                        
  # Print a section header so the output is easy to scan                                                                             
  info() { echo ""; echo "==> $*"; }
                                                                                                                                     
  # --------------------------------------------------------------------------
  # Docker Engine
  # --------------------------------------------------------------------------
  # We install from Docker's official apt repository, not Ubuntu's built-in                                                          
  # 'docker.io' package, because the official repo always has a current release.                                                     
                                                                                                                                     
  info "Installing Docker Engine"                                                                                                    
                                                                                                                                     
  # These packages allow apt to download over HTTPS and verify signatures                                                            
  sudo apt-get update -q
  sudo apt-get install -y -q ca-certificates curl                                                                                    
                                                                                                                                     
  # Create the directory where apt stores trusted signing keys                                                                       
  sudo install -m 0755 -d /etc/apt/keyrings                                                                                          
                                                                                                                                     
  # Download Docker's GPG key — this lets apt verify that packages                                                                   
  # actually come from Docker and haven't been tampered with
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \                                                                     
      -o /etc/apt/keyrings/docker.asc                                                                                                
  sudo chmod a+r /etc/apt/keyrings/docker.asc
                                                                                                                                     
  # Register Docker's package server as an apt source.                                                                               
  # $(dpkg --print-architecture) → "amd64" on most machines                                                                          
  # $(. /etc/os-release && echo "$VERSION_CODENAME") → "noble" on Ubuntu 24.04                                                       
  echo \                                                                                                                             
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \                                                
    https://download.docker.com/linux/ubuntu \                                                                                       
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null                                                                       
                                                                                                                                     
  sudo apt-get update -q
  sudo apt-get install -y -q \                                                                                                       
      docker-ce \           # The Docker daemon (background service)
      docker-ce-cli \       # The 'docker' command you type                                                                          
      containerd.io \       # Low-level container runtime Docker uses internally                                                     
      docker-buildx-plugin \# Extended builder (needed for multi-stage builds)                                                       
      docker-compose-plugin # Adds 'docker compose' subcommand (modern, no hyphen)                                                   
                                                                                                                                     
  # Add current user to the docker group so they can run docker without sudo.                                                        
  # The 'if' check makes this idempotent — running twice won't error.                                                                
  if ! groups "$USER" | grep -q docker; then                                                                                         
      sudo usermod -aG docker "$USER"                                                                                                
      echo "NOTE: You must log out and back in (or run 'newgrp docker') for"                                                         
      echo "      the docker group change to take effect in your current shell."                                                     
  fi                                                                                                                                 
                                                                                                                                     
  # --------------------------------------------------------------------------                                                       
  # hadolint — Dockerfile linter                        
  # --------------------------------------------------------------------------
  # hadolint is a single static binary, so we download it directly.
  # Pinning to a specific version means the script is reproducible.                                                                  
                                                                                                                                     
  info "Installing hadolint"                                                                                                         
                                                                                                                                     
  HADOLINT_VERSION="v2.12.0"                                                                                                         
  HADOLINT_BIN="/usr/local/bin/hadolint"
                                                                                                                                     
  # Only download if not already present at this version                                                                             
  if [[ ! -f "$HADOLINT_BIN" ]] || ! hadolint --version | grep -q "${HADOLINT_VERSION#v}"; then
      sudo curl -fsSL \                                                                                                              
          "https://github.com/hadolint/hadolint/releases/download/${HADOLINT_VERSION}/hadolint-Linux-x86_64" \
          -o "$HADOLINT_BIN"                                                                                                         
      sudo chmod +x "$HADOLINT_BIN"                     
  fi                                                                                                                                 
                                                        
  # --------------------------------------------------------------------------
  # pipx + flake8 — Python linter
  # --------------------------------------------------------------------------                                                       
  # pipx installs Python CLI tools in isolated virtual environments.
  # This avoids polluting the system Python and sidesteps Ubuntu 24.04's                                                             
  # restriction on 'pip install' without --break-system-packages.                                                                    
                                                                                                                                     
  info "Installing pipx and flake8"                                                                                                  
                                                                                                                                     
  sudo apt-get install -y -q pipx                                                                                                    
  pipx ensurepath
                                                                                                                                     
  # Install flake8 into its own isolated environment    
  if ! pipx list | grep -q flake8; then
      pipx install flake8                                                                                                            
  fi
                                                                                                                                     
  # --------------------------------------------------------------------------
  # Done
  # --------------------------------------------------------------------------

  info "All prerequisites installed. Versions:"                                                                                      
  git --version
  docker --version                                                                                                                   
  docker compose version                                
  hadolint --version
  # flake8 lives in ~/.local/bin — may need a new shell to appear on PATH
  export PATH="$HOME/.local/bin:$PATH"                                                                                               
  flake8 --version