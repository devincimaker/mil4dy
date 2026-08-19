# Original promo filter

Apply this to the visible chart title (the line that includes the track name, not the channel chip).

## Skip

Record the matching rule as the skip reason.

1. **Bootleg / mashup language** — title matches `\b(bootleg|mashup|mushup|unofficial)\b` (case-insensitive). Example: #67 *Thr1ll3r (FRASER Bootleg Remix)*.
2. **Leetspeak title** — the track name uses digits or `@` as letters (`0`/`1`/`3`/`4`/`5`/`7`/`@` substituting o/i/e/a/s/t/a). Example: *H0t 1n H3r3*, *D0n't 5t0p Th3 Mu51c*, *1n D@ Club*.
3. **Someone else's song, remixed** — `Title (Artist Remix|Edit|Flip|VIP)` or `Title - Artist Remix` where the named remixer is not the same person as the lead artist, or the base title is a well-known commercial recording (No Scrubs, Gin & Juice, Hot In Herre, Don't Stop The Music, Gasolina, Thriller, Scatman, Hollaback Girl, Better Off Alone, …).
4. **Explicit free-dl of a cover** — `*FREE DL*` / `*FREE DOWNLOAD*` on a remixed famous title. The badge alone is not enough to skip an original.

## Keep

Keep only when none of the skip rules match **and** the row looks like the uploader's own production:

- `Artist - Track`
- `Artist - Track (Original Mix|Extended Mix|Radio Edit)`
- Genre prefix plus that shape (`Tech House | Santino - Bora Bora`)

When unsure, skip with reason `ambiguous-not-original` rather than downloading.

## Chart snapshot (2026-08-18 Top 100)

Keep-set used to prove the flow. Re-filter live on later runs; ranks move.

| Rank | Title | `/d/` |
|------|--------|-------|
| 13 | Santino - Bora Bora | `bf6qtr` (exclusive) |
| 17 | Fred Dope - Feel The Rhythm | `38ynbe` (done 2026-08-18) |
| 49 | Santa Maria - MAMACITA | `4ak8mv` |
| 71 | ADIVTRIX - MI CALMA | `xtr5d9` |
| 72 | BARKER - Lucky Break (Radio Edit) | `n3zhaw` |
| 77 | RAINVILLE - Pop It (Extended Mix) | `7th47x` |
| 90 | AIN - DEEPER NIGHT | `psayc4` |
| 91 | Santa Maria - BANDIDA | `w6zhm3` |

Do not add REVL - GASOLINA. The title is a famous third-party recording.
