# LSD Dream Emulator — Wii forwarder channel

Builds `LSD Dream Emulator - LSDE [cmyksoda].wad`, a Wii channel that boots
straight into LSD: Dream Emulator through WiiStation.

```
./build/build.sh
```
> **About this file.** It is the build and modification log for the channel, and
> it doubles as the GPL "what was changed" record for the FCE Ultra GX
> components. Some prose below still names paths from the working tree it was
> written in (`images/channel/…`, `apps/`, `mGBA-GX-Channel-Forwarder-Project/`);
> those assets live in `icon/`, `banner/`, `splash/`, `audio/`, `SD/apps/` and
> `donor/` here. **The build scripts themselves now use the repository layout**,
> so nothing needs repointing — `build/build.sh` runs against a clean checkout
> and reproduces the committed `.wad` byte for byte.
>
> **`build/build.sh` will not run as-is from a fresh clone.** Three inputs are
> deliberately not redistributed here. The first two have fixed homes, so nothing
> needs repointing — create the directories and drop the files in:
>
> - `donor/FCE Ultra GX - FCEU [Tantric].wad`, the donor — get it from the
>   [FCE Ultra GX](https://github.com/dborth/fceugx) channel installer. Also
>   `donor/fceu_forwarder_content2.app`, which is that WAD's content 2 on its own;
>   `build/tools/extract.py` writes it as `build/extracted/content2.app`, so run
>   that first and copy it across.
> - `build/tools/benzin/BENZIN.EXE` and its `CYGWIN1.DLL`, which do the
>   `brlyt`/`brlan` XML round-trips. A Windows binary; runs under plain `wine`.
> - A Python venv with Pillow + pycryptodome, plus ImageMagick and `wine`.
>
> Everything else needed is in this repository. Each tool resolves these paths
> from its own file location rather than the working directory, so the scripts can
> be run from anywhere — previously `build_wad.py` and `extract.py` disagreed
> about where the donor lived, and neither path survived the project being moved.


Rebuilds everything from the assets in `images/` and `audio/`, then runs the
full verification pass. Needs `wine` (for Benzin), ImageMagick, and a Python
venv with Pillow + pycryptodome.

The banner and icon are authored for **16:9** and cropped by 4:3 — see
[Render sizes](#render-sizes--get-these-right-or-the-art-is-silently-cropped).

## What you need on the SD card

```
sd:/apps/LSD_Dream_Emulator/       <- the whole folder from ./apps
sd:/wiisxrx/                       <- from ./wiistation_unmodified
sd:/wiisxrx/isos/LSD.cue           <- the .cue is what gets listed, not the .bin
sd:/wiisxrx/isos/LSD.bin
sd:/wiisxrx/bios/SCPH1001.BIN      <- REQUIRED, see below
```

The release repo in `./LSD - Dream Emulator Forwarder Channel` carries that
whole tree ready to copy, as `SD/`, minus the two files that cannot be
redistributed.

**The BIOS is not optional.** With `wiisxrx/bios/` empty, WiiStation boots,
autoboots, and then dies loading the ROM with
`Invalid read from 0x1fc80000, PC = 0x80141954` — a loop reading little-endian
words off the end of an unloaded image. Dump it from your own PS1; it is Sony
copyright so it cannot ship here. WiiStation probes for `SCPH1000/1001/1002` and
`SCPH5500/5501/5502.BIN`.

Note also that WiiStation's autoboot does not fail safe: at `0x800ee358` it only
searches the ISO list when the count is `> 1`, otherwise it calls `load(0)`
regardless. A missing or unreadable ROM crashes rather than reporting an error.

Then install the WAD with your usual WAD manager. It needs a trucha-patched IOS,
same as any fakesigned channel.

The ISO filename only has to **contain** `LSD` — see the autoboot note below.

`apps/LSD_Dream_Emulator/meta.xml` carries
`<arguments>sd:/wiisxrx/isos, LSD</arguments>`, so
launching it from the Homebrew Channel autoboots the game too, not just the
channel.

**Keep meta.xml well-formed and pure ASCII.** HBC does not report a parse
error — it silently falls back to the *directory* name and "no description
available", which also means `<arguments>` is ignored and autoboot stops
working. The original file here contained `Mr.Nobody & Arcanearia`; a bare `&`
is invalid XML and killed the whole file. Escape it as `&amp;`, and avoid smart
quotes — every shipped meta.xml from Tantric and xjsxjs197 is 100% ASCII.
`verify.py` checks parseability, ASCII-ness, the `<name>`, and the arguments.

## Channel properties

```
Title ID      000100014C534445  ("LSDE")
Boot IOS      58
Contents      3   (banner archive / NAND loader stub / forwarder)
WAD size      1,734,976 bytes
Looks for     sd:/apps/LSD_Dream_Emulator/boot.dol
```

## How it is put together

Content 0 is the banner archive, content 1 is Tantric's NAND loader stub
(untouched, SHA-1 `e99125ee169e…`), content 2 is his forwarder with four
patches. The donor is **FCE Ultra GX**, chosen over Snes9x GX because its banner
is the smaller of the two — see the memory budget below.

| part | source | result |
|---|---|---|
| icon | `images/channel/icon/{bg1,bg2,bg3}.png` at **176×96** | 54,624 B |
| banner | `images/channel/banner/bg.png` at **832×456** | 796,448 B |
| sound | `audio/AMBIENT_00001.wav` | 86,216 B |

## Render sizes — get these right or the art is silently cropped

**The icon viewport is 128×96 and the banner's is 608×456 — in 4:3.** Art
authored larger is **centre-cropped, not scaled**. Tantric's icon
`Background.tpl` is 256×96, which is misleading — it is a scrolling tiled
pattern, so losing half of it is invisible. His real content all fits in 128×96
(120×48 logo, 36×36 sprites). A first build used 256×96 icon art and showed only
its middle half, reading as a 2× zoom.

**Those are the 4:3 numbers only. 16:9 widens the viewport by 4/3.** The Wii
renders an anamorphic 640×480 framebuffer that the TV stretches to 16:9, so the
System Menu shows 4/3 more *horizontal layout units* to keep proportions right.
The height never changes. Art authored at exactly the 4:3 width therefore shows
**black side bars** on a widescreen set.

| | 4:3 visible | 16:9 visible | authored at | keep content inside |
|---|---|---|---|---|
| icon | 128×96 | 170.67×96 | **176×96** | centre 128×96 |
| banner | 608×456 | 810.67×456 | **832×456** | centre 608×456 |

832 is not a guess: Nintendo's own full-bleed panes in the donor banner
(`StripePicture`, `TitleBarPicture`) are both exactly 832 wide — 810.67 rounded
up to the next multiple of 64. It is corroborated by the 16:9 splash rule below,
which pre-squashes art to 75% width — exactly the inverse of 4/3.

What matters is the **picture pane's width**, not the `lyt1` canvas: the donor
icon declares a 640×480 canvas yet renders in 128×96, so editing the canvas does
nothing. Widen the background pane and keep it centred at x=0.
`verify.py` asserts every visible pane matches the 16:9 viewport exactly — too
small bars, too large crops.

Because 4:3 sees only the middle, **anything that has to stay legible belongs in
the centre 128 (icon) or 608 (banner) columns.** `build/out/icon_preview_4_3.gif`
is that crop of the real animation, which is the quickest way to check it.

**`BackgroundMaterial` is not an identity material** in either archive:

| | banner | icon |
|---|---|---|
| `wrap_s` | `GX_MIRROR` | `GX_REPEAT` |
| `XScale` | **2.0** | 1.0 |
| `XTrans` | 0 (RLTS-animated) | 0.6 (RLTS-animated) |

Tantric tiles a 512-wide texture across a 1024-wide pane, hence scale 2. Dropping
in a full-width image without resetting `XScale` samples u over 0..2 and renders
it at half width, **mirrored**. Reset all of `wrap_s`/`wrap_t`/`XScale`/`YScale`/
`XTrans`/`YTrans`/`Rotate`, and match *any* wrap value — a rule that only
rewrote `GX_REPEAT` silently missed the banner's `GX_MIRROR`.

Watch inherited pane alpha too: `Logo00Pane` ships `alpha=b4` (180) and pane
alpha multiplies down the tree, so a repurposed pane caps its child at 70%.

### Icon

Four full-pane 176×96 layers: `Black` always opaque at the bottom, then
`Bg1`/`Bg2`/`Bg3` whose **pane alpha** is animated with `RLVC` (`type2="16"`).
Each layer fades in over 15 frames, holds 120 frames (2.0 s), fades out over 15,
and sits at 0 the rest of the cycle. Because one layer reaches 0 exactly as the
next starts rising, the composite passes through pure black — that is the dip.

```
framesize 450 (7.5 s at 60 fps), flags=01 (loop)
Bg1  0:0  15:255  135:255  150:0  450:0
Bg2  0:0 150:0    165:255  285:255 300:0 450:0
Bg3  0:0 300:0    315:255  435:255 450:0
```

All keyframe tangents are 0, which makes each segment a smoothstep rather than a
linear ramp — that is what makes the fade look soft. `build/out/icon_preview.gif`
is rendered from the real keyframes, so it shows what the Wii will show;
`icon_preview_4_3.gif` is its centre 128 columns, i.e. the same animation on a
4:3 set.

**The layers are CI8, not RGB565.** At the old 128×96 the photos fitted
comfortably as RGB565, but widening to 176 puts three RGB565 layers at 101,376
bytes of texture alone, which leaves under a kilobyte for the rest of the
archive against the hard cap below. CI8 with a per-image 256-entry palette is
17,472 bytes each instead of 33,856. At this size the quantisation is not
visible — decoding the built TPLs back and comparing against the sources shows
no difference worth the extra bytes. `Black.tpl` stays a 4×4 texture stretched
over its pane, so it costs 96 bytes at any pane width.

`tpl.quantize()` cannot do this on its own: it only collapses images that are
*already* inside the colour limit. `build_icon.palettize()` uses median cut with
Floyd–Steinberg dithering. TPL palette entries are RGB5A3 — RGB555 when opaque —
so the encoder rounds them a second time, which the comparison above includes.

Materials need no special setup: a stock brlyt material (`flags=0x111`, no
explicit TEV stages) already modulates the texture by vertex/pane alpha. Verified
by checking that Snes9x GX's `Banana00Mat`, which demonstrably fades, has
byte-identical flags.

### Banner

The banner is **derived from Tantric's layout** rather than emitted from scratch,
so that no section the Menu expects can go missing. `verify.py` asserts our
section list matches the donor's exactly:

```
lyt1 txl1 fnl1 mat1 <pan1/pas1/pic1/txt1/pae1 ...> grp1
```

Changes are kept to the smallest possible delta:

- `BackgroundPicture` resized to the full 832×456 and moved to the origin
- `BackgroundMaterial` reset to an identity texture matrix and `GX_CLAMP`
  (it ships `GX_MIRROR` + `XScale=2.0`; see above)
- every other pane gets `<visible>00</visible>` — 21 of them
- the `RLTS` texture scroll on `BackgroundMaterial` is flattened to 0 in both
  brlans, which are otherwise Tantric's untouched
- the 30 unused textures shrink to 4×4 stubs but **keep their names**, so every
  `txl1` entry and every brlan `RLTP` timg reference still resolves

`bg.png` is fully opaque, so it is stored **RGB565** rather than RGB5A3 — same
2 bytes/pixel, one more bit of green. Max per-channel quantisation error is 7/255.
The banner has no equivalent of the icon's hard cap, so it keeps full colour at
832×456 (758,784 bytes of texture) rather than palettizing.

## The icon size cap — this one bricks

**`icon.bin` must decompress to at most 0x19000 = 102,400 bytes.** This is a hard
check inside the System Menu, not a budget. Exceed it and you get a black screen
right after the Health & Safety screen, with Dolphin reporting
`Invalid write to 0x00000000`, `0x00000001`, `0x00000002` at a fixed PC.

The Menu (title `00000001/00000002`, `00000098.app`, data7 at `0x8132ffe0`) does
this at `0x81352488`:

```
lis   r4,2            ; 0x00020000
addi  r0,r4,-28672    ; 0x19000 = 102,400
cmpw  r3,r0
ble   ok
li    r3,-2           ; too big -> error, buffer never allocated
```

The destination pointer then stays NULL and the Menu's LZ77 decompressor at
`0x8155c2ac` runs regardless — the faulting instruction is `stb r3,0(r4)` at
`0x8155c328` in its literal-copy path, which is exactly why the writes march
0, 1, 2.

Tantric's icons cluster just under the line: 91,328 (Snes9x), 94,432 (FCEUGX),
97,664 (mGBA GX). A first attempt here used four 256×96 RGB565 layers —
196,864 bytes of texture, 198,976 total — and bricked Dolphin twice.

The fix was authoring the icon at its real viewport rather than 256×96, plus a
4×4 backdrop. Widening back out to 176 for 16:9 then re-crossed the line at
RGB565, so the photos moved to CI8:

| | first attempt | 4:3 build | this build |
|---|---|---|---|
| `Black` backdrop | 256×96 RGB565, 49,216 B | **4×4** RGB565, 96 B | **4×4** RGB565, 96 B |
| `Bg1`/`Bg2`/`Bg3` | 256×96 RGB565, 49,216 B each | 128×96 RGB565, 24,640 B each | **176×96 CI8, 17,472 B each** |
| **icon.bin total** | **198,976** ✗ | 76,128 (74% of cap) | **54,624** (53% of cap) |

For reference, three layers at the widths worth considering:

| 3 layers @ | RGB565 | CI8 |
|---|---|---|
| 172×96 | 99,072 — fits, with ~1 KB to spare | 51,264 |
| 176×96 | 101,376 — **over** once the rest of the archive is counted | 52,416 |

172 would just fit in RGB565 and still cover 16:9's 170.67, but on a 1.33-unit
margin. CI8 at 176 keeps the margin the art was authored for and comes in at
half the cap, which is the better trade here. (`tpl.py`'s CI4/CI8 support was
verified byte-exact against the real palettized TPLs in the mGBA GX v2 banner.)

`build_icon.py` asserts the cap and `verify.py` re-checks it on the finished WAD.

A missing `grp1` was an earlier theory for the same crash and was **wrong** —
adding it changed nothing. Deriving layouts from a donor is still worth doing,
but it is not what fixed this.

If a bad WAD does take out Dolphin, the NAND on Linux is at
`~/.local/share/dolphin-emu/Wii/` — move `title/00010001/4c534445` and
`ticket/00010001/4c534445.tik` aside and the Menu boots again.

### Sound

`sound.bin` is a mono BNS at 22,050 Hz with the **loop flag off**, so it plays
once. Nintendo DSP ADPCM (codec 0): 14 samples per 8-byte frame, hence the
1.75 samples/byte ratio the verifier checks — if you ever compute something else
you have misread the codec field.

ffmpeg has no encoder for this format, so `tools/build_sound.py` implements one.
The eight predictor pairs are order-2 LPC fits over eight equal segments of the
file, quantised to Q11; each frame then picks the best (predictor, scale) pair.
Round-trip SNR is 44.4 dB.

### Forwarder

Four in-place edits; the DOL keeps its original 934,656 bytes.

| what | where |
|---|---|
| 4:3 splash PNG | `0x081700`, 165,683 B of room |
| 16:9 splash PNG | `0x0A9E40`, 157,270 B of room |
| app path string | relocated, reference at `0x8124b4b0`/`0x8124b4c0` repointed |
| command line | `0x8124b5ac` block replaced, `argc` at `0x8124b5e4` set to 3 |

**The app path could not be patched in place.** Tantric's
`%s:/apps/fceugx/boot.dol` has only 3 spare bytes before the next string, which
caps the folder name at 9 characters — `LSD_Dream_Emulator` is 18. The string is
instead written into dead space and its single `lis`/`addi` reference repointed.

**Autoboot.** WiiStation only autoboots when it receives `argc >= 3`.

`argv[1]` is **the directory to search, not a device name** — this is the one
thing that is easy to get wrong. Inside the SD init, gated on the autoboot flag,
`0x80015f5c` does `strncpy(isoDir->name, argv[1], 256)`, overwriting WiiStation's
own `sd:/wiisxrx/isos` string at `0x80297A38`. The separate
`strcasestr(argv[1], "sd:/")` at `0x800ee328` only chooses SD vs USB, and a full
path satisfies it too. Passing a bare `sd:/` makes WiiStation list the card root,
match nothing, and boot to a black screen.

`argv[2]` is `strcasestr`'d against each entry of the scanned ISO list, so it is
a case-insensitive substring of the filename. If nothing matches, the loop loads
the *last* entry anyway; if the list has one entry or fewer it calls `load(0)`
blindly. Both look identical from the couch: black screen.

Tantric's forwarder builds a one-entry command line, so the `malloc`/`strcpy`
block is replaced with a pointer to a static blob and a length:

```
sd:/apps/LSD_Dream_Emulator/boot.dol\0 sd:/wiisxrx/isos\0 LSD\0 \0   (length 59)
```

devkitPPC's `build_argv()` re-derives argc/argv from `commandLine` + `length`, so
only those two fields have to be right. Two instructions that would have written
into the static blob are NOPed out.

If autoboot ever fails you land in WiiStation's own menu — it is not a brick.

**Relocated data** lives in the tail of the 16:9 splash region. libpng stops at
the `IEND` chunk, so bytes after the replacement PNG are never read. That is
safer than the 898-byte zero run at `0x0e37ee`, which may be live `.data`.

**Splashes must stay colortype 2.** PNGU rejects palette PNGs outright, so the
usual trick of palettizing to shrink them is unavailable, and the replacement
must be **≤** the original byte length. The source scan costs ~609 KB stored
losslessly because of its dense dithered pattern, so it is de-noised first with
`-kuwahara 2 -despeckle -posterize 24` (edge-preserving, so the logo and the
"Lovely Sweet Dream" text stay legible). `patch_forwarder.py` walks a quality
ladder and stops at the first setting that fits.

## Banner memory budget — read before adding art

Total **uncompressed** banner memory across all installed channels is a hard
constraint. Exceed it and the Wii Menu slows and then hard-freezes while paging
the channel grid with `+`/`-`. It is not a brick, and no structural check
detects it. Roughly: one ~2.5 MB banner is survivable, two are not.

This channel's banner is **796,448 bytes — 57% of FCEUGX's 1,388,896**, so there
is still headroom. (It was 555,488 before the widescreen rebuild; going from
608×456 to 832×456 costs 204,288 bytes of texture.) If you add art, keep it
under that FCEUGX figure. To
shrink without touching the art, palettize to CI4/CI8 with one shared palette per
sprite; texture format is invisible to the layout, so no pane edits are needed.

## Toolchain

The previous project drove `libWiiSharp.dll` from 32-bit PowerShell, which does
not exist here. `build/tools/` reimplements it for Linux:

- `wiilib.py` — WAD container (AES-CBC contents, trucha fakesigning), U8, LZ77
  type 0x10, IMD5, IMET
- `tpl.py` — TPL encode/decode, RGB565 / RGB5A3 / RGBA8 / CI4 / CI8
- `build_sound.py` — DSP ADPCM encoder
- Benzin still handles brlyt/brlan XML, under plain `wine`

Everything was validated by byte-exact round-trip against the stock FCEUGX WAD
before being trusted: the container rebuilds byte-identically when re-signing is
skipped, inner U8 archives and every TPL format round-trip exactly, and the LZ77
encoder lands within 0.2% of Tantric's.

Two traps worth repeating:

- **Never build a U8 from a directory tree.** libWiiSharp's `FromDirectory`
  wrote garbage directory parent indices and bricked the System Menu with a black
  screen after the Health & Safety screen, passing every obvious check on the
  way. Always mutate a loaded archive. `verify.py` asserts the parent indices.
- **brlyt pane names are a fixed 16-byte field** that silently overflows into the
  8-byte `userdata` field. `BackgroundPicture` is 17 characters and truncates to
  `BackgroundPictur`, which would desync it from the brlan that names it — hence
  `BackgroundPic`. `verify.py` checks for the spill.

## Verification

`tools/verify.py` reads the finished WAD back off disk and checks content SHA-1s
against the TMD, both trucha signatures, the title ID against a reserved list,
IMET MD5 and sizes, U8 parent indices in all three archives, that every texture
and material a layout references exists, that every pane a brlan animates exists,
4-pixel texture alignment, the banner budget, the BNS ratio and loop flag, and
every forwarder patch. Run it before installing anything.

#### AI Disclosure

The entirety of *this* `.md` file was generated using Claude Code.
