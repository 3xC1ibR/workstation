---
name: radio-alarm
description: Schedule live internet radio on this Mac with a gradual volume increase, or inspect, change, or cancel a previously scheduled radio alarm. Use for radio wake-up requests; excludes reminders that do not play audio and playback on other devices.
---

# Radio alarm

Schedule actual local playback that survives the conversation ending. Use macOS launchd, caffeinate, Python, and FFplay. A skill supplies the workflow; the installed local job performs the timed action.

## Resolve the request

Read the current local date, time, and timezone. Resolve the requested start into an explicit date and timezone and state that interpretation. Use context to resolve AM/PM; ask when a consequential ambiguity remains. Do not silently roll a past time into another day.

Honor the user's station, city exclusions, start time, and fade duration. If a random station is requested, randomly select among eligible larger cities, then verify that station and its current direct audio stream through its official website. Do not treat the example below as a universal station preference.

Default to a 30-minute fade with system output capped at 10%, reflecting the user's preference for a much quieter, more gradual alarm. Keep system output at 10% throughout playback and fade the player signal from 1% gain to full gain in equal decibel increments. Honor explicit overrides and state the chosen settings. Do not change current system volume during setup. Updating this skill changes future alarms; apply changes to an existing alarm only when requested, since its runner may already be running.

## Install one local job

Find a working Python interpreter and FFplay executable. On this Mac, `/usr/bin/python3` worked when Homebrew Python's plistlib import failed due to a libexpat mismatch; `/opt/homebrew/bin/ffplay` was available. Check current availability instead of assuming those paths work everywhere. Do not install dependencies unless installation is within the user's request.

Put each alarm's configuration, runner, logs, and status in a unique directory under `~/.local/state/npr-radio/`. Keep mutable alarm state outside the skill directory. Store an explicit timezone-aware timestamp and target epoch, stream URL, station label, fade seconds, system-volume cap, initial player gain, fade curve, and launchd label in configuration.

Generate a unique LaunchAgent plist under `~/Library/LaunchAgents/`. Use argument arrays, absolute executable paths, `RunAtLoad: true`, and `KeepAlive: false`. Run `/usr/bin/caffeinate -i -s <python> <runner>` so the runner can wait for its target without model polling. Redirect stdout and stderr to this alarm's files. Register it with `launchctl bootstrap gui/<uid> <plist>`.

The runner should:

1. Write a scheduled status with the exact date and station, then wait until the target epoch.
2. Skip stale alarms after a stated grace period, such as 30 minutes. Use an atomic started marker to prevent duplicate playback, and honor a cancellation marker.
3. Remove the persisted plist once execution is claimed, so a later login does not replay the alarm.
4. At playback time, unmute and set the system-volume cap with AppleScript. For the default 10% cap: `set volume output volume 10 without output muted`. Keep that system setting fixed while the player fades in.
5. Start FFplay with a player window titled with the station and how to stop it. Apply the gradual gain inside the player. Keep playback going at the final gain after the fade ends unless the user requested a stop time.
6. Record the player PID and status. Bound startup retries; preserve elapsed fade time across retries. Treat a normal player close as a stop, not a reason to restart it.

For the default 30-minute fade from -40 dB (0.01 player gain) to 0 dB (full player gain), use this FFmpeg filter as one subprocess argument:

```text
asetpts=PTS-STARTPTS,volume='if(isnan(t),0.01,pow(10,-2+2*min(1,max(0,t/1800))))':eval=frame
```

Here, 1800 is the fade duration in seconds. Player gain is approximately 0.01 at the start, 0.032 after 7.5 minutes, 0.10 after 15 minutes, 0.316 after 22.5 minutes, and 1 after 30 minutes. Equal decibel increments keep the signal quiet early in the fade while completing the increase over the requested duration. System volume stays at 10% after the fade ends; reaching full player gain does not mean 100% system volume. These are gain settings, not calibrated perceived loudness. On retries, add elapsed playback time to `t` and use the corresponding current gain in the NaN branch so reconnecting never resets the fade.

Useful FFplay options include `-autoexit`, `-window_title`, `-showmode waves`, `-rw_timeout 15000000`, `-reconnect 1`, `-reconnect_streamed 1`, and `-reconnect_delay_max 5`. Pass URLs and other user values through subprocess argument arrays, not shell interpolation.

Create a cancellation helper that marks only this alarm cancelled, removes its persisted plist, and runs `launchctl bootout gui/<uid>/<label>`. Stopping the owned job should stop its player and release its caffeinate assertions. Do not use broad process-name kills.

## Verify and report

Validate the plist with `plutil -lint`; compile the runner without executing its playback branch. Decode a short live-stream sample and validate the gain filter with FFmpeg output directed to the null sink. Compile the volume AppleScript without running it during setup. If checking FFplay's audio path, keep it muted and enforce an external timeout: `ffplay -t` did not reliably exit a live stream in the original setup.

After registration, inspect the exact launchd label, scheduled status, error log, and `pmset -g assertions`. Confirm that the job is active and the target matches the request. Report what is scheduled; claim successful playback only after observing the player and its logs at execution time.

Explain that the Mac must stay powered, connected to the internet, and logged in with its lid open. Caffeinate permits display sleep but does not guarantee waking a shut-down Mac or overriding a closed lid. Do not promise a hardware wake event unless one was actually installed.

Provide the exact start date/time, selected station, fade duration, endpoint, and how to stop or cancel. For later inspection or cancellation, read the existing configuration and job state before modifying anything. Do not create a second alarm merely to answer a status question.

## Verified stream example

KQED, San Francisco: `https://streams.kqed.org/kqedradio.mp3`.
Official stream guidance: <https://www.kqed.org/radio/audio-help/>. Recheck it when scheduling rather than treating a saved URL as permanently valid.
