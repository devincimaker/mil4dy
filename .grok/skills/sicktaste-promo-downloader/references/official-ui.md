# Official Sick Taste listener UI

Listener downloads do **not** use the WordPress admin login. Artist login is only for exclusive pages and for creating download pages.

## Chart → download page

1. Open the chart.
2. Each row's **Free download** is `https://sicktaste.com/d/{id}/` (`a.wmp-chart-get`).
3. Work on the full `/d/{id}/` page. The chart drawer iframe (`?wmp_embed=1`) is the same app but harder to drive.

## Steps on `/d/{id}/`

Visible step is a `.wmp-step` with `display:block`.

| Step id | What you see | Action |
|---------|----------------|--------|
| exclusive gate | "This is an exclusive download. Log in or sign up for free to access." | In-page **Log in** modal (email/password), not `wp-login.php`. Wait for **Start download**. Once signed in, exclusive pages skip the email step. |
| `#wmpIntroStep` | **Start download** (`#wmpStartBtn`) | Click it. |
| `#wmpEmailStep` | **Your email address** + **Get the track** | Fill the configured email. Submit. Copy says the artist receives the email. Not every track shows this. |
| `#wmpSocialStep0` | **Like this track** (sometimes **Repost**) + **Connect SoundCloud** | Click **Connect SoundCloud** unless the button has class `is-done`. While a popup is open the button is `is-busy` / disabled — do not retry-click; switch to the existing `secure.soundcloud.com/authorize` tab and click **Allow**. The popup closing is success. |
| `#wmpUnlockedStep` | **Download** (`#wmpDownloadBtn`) | Register `download` first, then click. Hosted file is often Dropbox `dl=1`. Keep the served filename. |

The email POST goes to `wp-admin/admin-ajax.php` and may include `download_url` in JSON. Do not fetch that URL yourself. Click **Download**.

## SoundCloud popup

- Playwright: wait for a new page after **Connect SoundCloud**.
- Click **Allow** on "Allow Sick Taste access to your SoundCloud account?".
- The authorize tab closing is success, not a crash.
- If SoundCloud is signed out, stop and tell the user to sign in in that tab.

## Locators that worked on 2026-08-18

- Start: `getByRole('button', { name: 'Start download' })`
- Email: `getByRole('textbox', { name: 'Your email address' })`
- Submit email: `getByRole('button', { name: 'Get the track' })`
- SoundCloud: `getByRole('button', { name: 'Connect SoundCloud' })`
- File: `getByRole('link', { name: 'Download', exact: true })`
