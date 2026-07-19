# SKAsia EPG for IPTVX

This repository creates two externally hosted XMLTV URLs for the two SKAsia Xtream accounts while keeping both playlists configured as **Xtream** in IPTVX.

## Files produced

- `output/skasia-m240730254672129-epg.xml`
- `output/skasia-m240730582462128-epg.xml`
- Compressed `.xml.gz` copies
- `output/build-status.txt`

Both accounts currently have the same channel catalogue, so the generated guide content is identical. Separate filenames are provided so each IPTVX account can have its own URL.

## Upload this repository to GitHub

1. Create a new **public** repository. Suggested name: `SKAsia-EPG`.
2. Upload all files and folders from this package, including the hidden `.github` folder.
3. Open the repository's **Actions** tab.
4. Select **Update SKAsia EPG**.
5. Select **Run workflow**.
6. Wait for it to finish. The workflow downloads and merges the current XMLTV feeds, then commits the generated files into `output/`.

## Enable GitHub Pages

1. Open **Settings → Pages**.
2. Under **Build and deployment**, choose **Deploy from a branch**.
3. Select branch **main** and folder **/ (root)**.
4. Save and wait for the Pages deployment.

Your IPTVX URLs will follow this format:

```text
https://YOUR-GITHUB-USERNAME.github.io/SKAsia-EPG/output/skasia-m240730254672129-epg.xml

https://YOUR-GITHUB-USERNAME.github.io/SKAsia-EPG/output/skasia-m240730582462128-epg.xml
```

Replace `YOUR-GITHUB-USERNAME` with your actual GitHub username. Your GitHub sign-in email is not necessarily your username.

## Add each URL to IPTVX

For each existing SKAsia Xtream playlist:

1. Edit the playlist.
2. Keep the existing server, username and password unchanged.
3. Replace the provider's `xmltv.php` address in the EPG field with the matching GitHub Pages URL.
4. Keep **EPG Shift** at `0`.
5. Use a daily refresh interval when available.
6. Save, then refresh the playlist and EPG.

## Important technical limitation

This project merges broad public XMLTV sources. It cannot guarantee schedules for provider-created event channels, backup feeds, test streams, renamed channels or channels for which no public listings exist.

A green “EPG URL verified” message only confirms that IPTVX can reach and parse the URL. Matching still depends on the channel identifiers and names used by the Xtream server. Because SKAsia leaves many EPG identifiers blank, IPTVX may not automatically associate every merged listing. Full matching may require a channel-remapping proxy or a provider-side correction.
