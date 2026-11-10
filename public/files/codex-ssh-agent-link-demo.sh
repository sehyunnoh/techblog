#!/usr/bin/env bash
# Reproduces the "stable symlink" pattern that openai/codex issue #59694 quotes from
# the Codex Desktop SSH bootstrap. The refresh() body below is copied from that issue
# (paths shortened); it is NOT extracted from the desktop app, which is closed source.
#
# A long-lived "app-server" is modelled as a process whose SSH_AUTH_SOCK was fixed at
# launch. We probe it by running `ssh-add -l` with that frozen value.
# Needs: bash, OpenSSH (ssh-agent, ssh-add, ssh-keygen), coreutils `timeout`. Linux/WSL.
set -u
W=$(mktemp -d)
LINK=$W/forwarded-ssh-agent.sock
ssh-keygen -q -t ed25519 -N '' -f "$W/key" >/dev/null

start_agent() {   # $1 = socket path; prints agent pid
  ssh-agent -D -a "$1" >/dev/null 2>&1 &
  local pid=$!
  for _ in $(seq 50); do [ -S "$1" ] && break; sleep 0.1; done
  SSH_AUTH_SOCK=$1 ssh-add -q "$W/key" 2>/dev/null
  echo $pid
}
end_session() {   # what sshd does when a forwarded session ends
  kill -9 "$1" 2>/dev/null; wait "$1" 2>/dev/null; rm -f "$2"
}
probe() {         # $1 = label, $2 = SSH_AUTH_SOCK value the "app-server" holds
  local out rc
  out=$(SSH_AUTH_SOCK=$2 timeout 3 ssh-add -l 2>&1); rc=$?
  case $rc in
    0)   echo "  $1: OK    ($(echo "$out" | awk '{print $4}'))";;
    124) echo "  $1: HANG  (no answer within 3 s)";;
    *)   echo "  $1: FAIL  (rc=$rc, $(echo "$out" | head -1))";;
  esac
}
# --- copied from the issue's quoted bootstrap, variables inlined -------------------
refresh() {       # runs once per desktop connection, with that connection's SSH_AUTH_SOCK
  if [ -S "${SSH_AUTH_SOCK:-}" ]; then
    ln -sfn -- "$SSH_AUTH_SOCK" "$LINK"
  elif [ ! -S "$LINK" ]; then
    rm -f -- "$LINK"
  fi
}
# -----------------------------------------------------------------------------------

echo "== E0: before the link. app-server keeps the socket path of the session that started it"
A=$W/sshd-A.sock; PA=$(start_agent "$A")
FROZEN=$A
probe "app-server, session A alive" "$FROZEN"
end_session $PA "$A"
B=$W/sshd-B.sock; PB=$(start_agent "$B")     # reconnect: a NEW forwarded socket path
probe "app-server, after A ended and B connected (frozen path)" "$FROZEN"
probe "a fresh shell in session B (for contrast)" "$B"
end_session $PB "$B"

echo; echo "== E1: with the link. app-server launched with SSH_AUTH_SOCK=\$LINK"
A=$W/sshd-A.sock; PA=$(start_agent "$A")
SSH_AUTH_SOCK=$A refresh
probe "session A connected" "$LINK"
end_session $PA "$A"
B=$W/sshd-B.sock; PB=$(start_agent "$B")
SSH_AUTH_SOCK=$B refresh
probe "A gone, B connected (link refreshed)" "$LINK"

echo; echo "== E2: two clients at once. B connects while A is still working"
A=$W/sshd-A.sock; PA=$(start_agent "$A")
SSH_AUTH_SOCK=$A refresh
probe "only A connected" "$LINK"
echo "  link -> $(basename "$(readlink "$LINK")")"
# B is still alive from E1 and now connects as the second client
SSH_AUTH_SOCK=$B refresh
echo "  link -> $(basename "$(readlink "$LINK")")  (A's session never ended)"
probe "A's work after B connected (goes through B's agent)" "$LINK"
end_session $PB "$B"
probe "B disconnects, A still connected" "$LINK"
SSH_AUTH_SOCK=$A refresh
probe "...until A happens to reconnect" "$LINK"
echo "  (A's own agent was healthy the whole time:)"; probe "A's agent, direct" "$A"

echo; echo "== E3: B's forwarded socket exists but never answers (issue #59694's symptom)"
B=$W/sshd-B.sock; PB=$(start_agent "$B"); kill -STOP $PB
SSH_AUTH_SOCK=$B refresh
echo "  [ -S B ] = $([ -S "$B" ] && echo true || echo false)  (the only liveness check in refresh)"
echo "  link -> $(basename "$(readlink "$LINK")")"
probe "app-server via link" "$LINK"
probe "A's agent, direct" "$A"
kill -CONT $PB; end_session $PB "$B"; end_session $PA "$A"

echo; echo "== E4: a client without any agent connects"
A=$W/sshd-A.sock; PA=$(start_agent "$A")
SSH_AUTH_SOCK=$A refresh
SSH_AUTH_SOCK= refresh
probe "link survives a no-agent client while A is alive" "$LINK"
end_session $PA "$A"
SSH_AUTH_SOCK= refresh
echo "  after A ends and a no-agent client connects: link exists? $([ -e "$LINK" ] || [ -L "$LINK" ] && echo yes || echo no)"
rm -rf "$W"
