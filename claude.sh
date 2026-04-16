#!/usr/bin/env bash
set -euo pipefail

systemd-inhibit --what=idle --who=claude --why="Session active" -- claude --allow-dangerously-skip-permissions --model opus --effort max
