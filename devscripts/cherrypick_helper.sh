#!/bin/bash

echo -n "Paste repo link (will trim for you): "
read X
X="${X/yt-dlp*/yt-dlp}"
echo -e "\nUsing: $X"
git remote remove temp 2>/dev/null
git remote add temp "$X" || exit 1
git fetch --depth=30 temp || exit 1
echo "Paste cherry-picks here, sh for a shell, exit to stop"
while read -r X
	do
	[ -z "$X" ] && continue
	[ "$X" = "exit" ] && break
	if [ "$X" = "sh" ]; then bash; continue; fi
	git cherry-pick $X
done
echo "Exiting."
