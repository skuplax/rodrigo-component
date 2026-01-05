# Setting up Spotify App for Mopidy-Spotify

Since the mopidy.com authentication page isn't loading, you can use your own Spotify app from developer.spotify.com. Here's how to configure it:

## Step 1: Create/Configure Your Spotify App

1. Go to https://developer.spotify.com/dashboard/
2. Log in with your Spotify account (must be Premium)
3. Click "Create app" or select your existing app
4. Fill in:
   - **App name**: e.g., "Mopidy-Spotify"
   - **App description**: "Mopidy music server integration"
   - **Redirect URI**: Add one of these:
     - `http://localhost:6680/mopidy/spotify/callback`
     - `http://localhost:6680/`
     - `http://127.0.0.1:6680/mopidy/spotify/callback`
   - **What are you building?**: Select "Web API" or "Non-commercial"

## Step 2: Get Your Credentials

1. In your app dashboard, click "Settings"
2. Copy your **Client ID**
3. Click "Show client secret" and copy your **Client Secret**

## Step 3: Update Mopidy Configuration

Edit `/etc/mopidy/mopidy.conf` and ensure the `[spotify]` section has:

```ini
[spotify]
enabled = true
client_id = YOUR_CLIENT_ID_HERE
client_secret = YOUR_CLIENT_SECRET_HERE
bitrate = 160
volume_normalization = true
timeout = 10
allow_cache = true
cache_size = 8192
allow_playlists = true
```

## Step 4: Restart Mopidy

```bash
sudo systemctl restart mopidy
```

## Step 5: Verify Authentication

Check the logs:
```bash
sudo journalctl -u mopidy -n 50 | grep -i spotify
```

You should see successful authentication messages. If you see "invalid_client", double-check:
- Client ID and Secret are correct
- Redirect URI is set in your Spotify app
- App is not in "Development Mode" with restricted users (or add your Spotify account as a user)

## Troubleshooting

- **"invalid_client Client not known"**: Verify credentials are correct and app is active
- **"Authorization failed"**: Check redirect URI matches what's configured
- **"Failed to load Spotify user profile"**: Ensure your Spotify account is Premium

