#!/bin/bash
# Spotify OAuth Authorization with SSH Port Forwarding Instructions
# 
# STEP 1: Set up SSH port forwarding (run this on your LOCAL machine):
#   ssh -L 6680:127.0.0.1:6680 jonas@192.168.1.22
#
# STEP 2: Keep that SSH session open, then open the URL below in your browser

CLIENT_ID="93a729141d0d4a8bab606d215545a0c0"
REDIRECT_URI="http://127.0.0.1:6680/mopidy/spotify/callback"
SCOPE="user-read-private user-read-email user-library-read user-library-modify user-read-playback-state user-modify-playback-state user-read-currently-playing streaming playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private user-follow-read user-follow-modify user-read-recently-played user-top-read"

AUTH_URL="https://accounts.spotify.com/authorize?client_id=${CLIENT_ID}&response_type=code&redirect_uri=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${REDIRECT_URI}'))")&scope=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${SCOPE}'))")"

echo "=========================================="
echo "Spotify OAuth Authorization"
echo "=========================================="
echo ""
echo "IMPORTANT: First set up SSH port forwarding!"
echo ""
echo "On your LOCAL machine, run:"
echo "  ssh -L 6680:127.0.0.1:6680 jonas@192.168.1.22"
echo ""
echo "Keep that SSH session open, then:"
echo ""
echo "1. Open this URL in your browser:"
echo ""
echo "${AUTH_URL}"
echo ""
echo "2. Log in with your Spotify Premium account"
echo "3. Authorize the application"
echo "4. You'll be redirected back to Mopidy (via port forwarding)"
echo ""
echo "To check if authorization succeeded, run on the Pi:"
echo "  sudo journalctl -u mopidy -f | grep -i spotify"
echo ""

