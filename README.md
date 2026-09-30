# cookie-clicker-linux
# Cookie

An idle cookie-baking game for the terminal. Click a cookie, buy things that click it for you, and
come back later to find the bakery has been busy.

```
 1.23 million cookies  26.3/s
────────────────────────────────────────────────────────────────────────────────
                                 .-"""""""""-.
                                .'  o     .   '.
                               /   .   o     o  \
                              |  o    .   .      |
                              |     o     o   .  |
                               \  .    o     .  /
                                '.   o    .   .'
                                  '-.........-'
────────────────────────────────────────────────────────────────────────────────
 Upgrades: Reinforced index finger (150)   Carpal tunnel prevention cream (750)
────────────────────────────────────────────────────────────────────────────────
 Grandmas have formed a committee. Minutes unavailable.
 Cursor          23               374             2.3/s    9%
 Grandma          8               306               8/s   30%
 Farm             2     1.46 thousand              16/s   61%
 ???
 ???
 ???
 space Bake  x Buy  s Stats  a Awards  p Ascend  , Settings  ? Help  q Quit
```

## Features

- 32 building tiers, from a Cursor to The Recipe, each at `cost x 1.15^owned`. The last
  five cost sixty to a hundred times the tier below and are meant to take weeks.
- 184 upgrades: five doublings per building, click power, global multipliers, and golden
  cookie lures.
- 91 achievements, each worth a permanent 1% to production, with a screen listing
  what you have and what is left.
- A news ticker that comments on what you actually own.
- Golden cookies that appear on their own schedule and pay out if you are watching.
- Ascension: trade a run for heavenly chips and a permanent multiplier.
- Offline progress at half rate, capped at a day, with a summary on the way back in.
- Numbers formatted up to a decillion and then in scientific notation, never wider than the column.
- Mouse and keyboard throughout, and a readable layout at 80x24.
- Six themes, including one that uses your terminal's own colours.
- Updates in place with `cookie --update`, which never touches your save.

## Installing

Requires Python 3.12 or newer. On Arch Linux:

```sh
# pipx
sudo pacman -S python-pipx
pipx install .

# or uv
sudo pacman -S uv
uv tool install .
```

Either one puts a `cookie` command on your `PATH`. `pipx uninstall cookie` and
`uv tool uninstall cookie` remove it again.

## Playing

```sh
cookie
```

| Key | What it does |
|---|---|
| `space`, `enter`, click the cookie | Bake one cookie by hand |
| `g`, click the prompt | Catch a golden cookie while one is on screen |
| `up`, `down` | Move through the building list |
| `home`, `end`, `pageup`, `pagedown` | Jump around the building list |
| `x`, click a row | Buy the selected building |
| `1`, `2`, `3`, `4` | Buy 1, 10, 100, or as many as you can afford |
| `b` | Buy the best building you can afford |
| `u` | Buy the cheapest available upgrade |
| `s` | Statistics |
| `a` | Achievements, earned and still to earn |
| `p` | Ascend |
| `,` | Settings, export, import, and reset |
| `?` | Help |
| `escape` | Close a screen |
| `q`, `ctrl+c` | Save and quit |

A building you cannot nearly afford shows as `???` until your lifetime total reaches half its price.

Holding the bake key does not auto-click. A terminal sends no key-up event, so a held key arrives as
a stream of ordinary presses; anything arriving faster than a person can tap is treated as the key
being held and bakes once, not continuously.

### Themes

Set in the settings screen (`,`):

| Theme | What it looks like |
|---|---|
| `classic` | Warm browns. The default. |
| `night` | Dark night blue. |
| `terminal` | Your terminal's own colours, so the game matches whatever scheme you already use. |
| `system` | Light or dark, taken from the terminal's `COLORFGBG`. Dark when the terminal does not say. |
| `mono` | Greyscale. |
| `high_contrast` | Black, white, and pure primaries. |

Most terminals never set `COLORFGBG`, and there is no portable way to ask one what its background is,
so `system` falls back to dark. If your terminal is light and `system` guesses wrong, pick `terminal`
instead and the game will use your palette directly.

### Command line

```sh
cookie --where              # print the save location
cookie --export FILE        # write the current save to FILE
cookie --import FILE        # replace the current save with FILE
cookie --save-dir DIR       # use a different save directory
cookie --seed N             # fix the random seed of a new game
cookie --update             # install the newest release from GitHub
cookie --wipe               # start again from nothing
cookie --yes                # answer the confirmation for --update or --wipe
cookie --theme night        # set the colour theme and keep it
cookie --list-themes        # list the themes
cookie --stats              # print a summary of the save and exit
cookie --stop               # stop a copy left running in another terminal
```

`cookie --stop` is for the way this ends up being used: started in a terminal or a tmux pane and
forgotten about. It finds the running instance through the pid it recorded next to the save, sends it
`SIGTERM`, and waits. That is the same route as closing the terminal, so the instance saves on the
way out rather than being killed mid-tick.

`cookie --stats` is meant for the way this game is actually used: left running, glanced at. It reads
the save and prints the statistics screen without starting the interface.

#### Updating

```sh
cookie --update
```

It asks GitHub for the newest release, compares it with what you have, shows you the exact install
command, and asks before running it. Your save is not part of the install: it lives in the data
directory and the installer only replaces the code, so updating cannot lose progress.

The installer it uses is whichever one you installed with, detected from where the code is running:
pipx, uv, or pip. Running it from a script needs `--yes`, because a non-interactive run refuses
rather than assuming consent. Point it at a fork with `COOKIE_REPO=owner/name`.

#### Starting over

```sh
cookie --wipe
```

Clears cookies, buildings, upgrades, achievements, and chips, and keeps your settings. It asks you to
type `WIPE` first, and the save it replaces is rotated into `save.json.bak.1`, so a wipe you regret
is still on disk. There is the same thing inside the game, under settings.

## Saves

The save lives at `$XDG_DATA_HOME/cookie/save.json`, or `~/.local/share/cookie/save.json` when
`XDG_DATA_HOME` is unset. `cookie --where` prints the path.

The game saves every 30 seconds, when you quit, and on `SIGINT`, `SIGTERM`, or `SIGHUP`, so closing
the terminal keeps your progress.

A running game also writes its process id to `cookie.pid` in the same directory and removes it on the
way out, which is how `cookie --stop` finds it. A pid file left behind by a crash is ignored and
cleaned up: the number is checked against the process that actually holds it first.

Writes are atomic: the file is written to a temporary path, forced to disk, and then renamed over the
old one, so an interrupted save cannot leave a half-written file. Before each save the current file is
copied to `save.json.bak.1` and the older backups rotate down to `save.json.bak.3`.

On startup the game reads the main save, and if it is unreadable or its checksum does not match, it
tries each backup in turn and tells you what it found. A file it cannot use is renamed to
`save.json.corrupt.<timestamp>` rather than deleted. The format carries a version and a migration
chain, so a save written by an older release is brought forward rather than rejected.

## Project layout

```
src/cookie/
  engine/       pure game logic: content, state, costs, ticks, unlocks, prestige
  persistence/  save format, atomic writes, backups, migrations
  ui/           Textual widgets and screens
  session.py    the clock, the autosave timer, and the shutdown path
  updater.py    checking GitHub for a release and installing it
  app.py        the Textual application
  cli.py        the command line
docs/
  ARCHITECTURE.md   module boundaries, the tick contract, the save protocol
  BALANCE.md        every number, and the pacing the simulation test asserts
  DEVELOPING.md     the gate, the load-bearing invariants, and what is still open
tests/
```

`engine/` imports nothing outside the standard library and nothing from the other layers, which is
what lets six hours of play be simulated in four seconds. `tests/test_layering.py` enforces it.

## Development

```sh
uv sync                              # create the environment
uv run pytest                        # tests, including the pacing simulation
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict src tests
uv run python -m cookie              # run without installing
```

## Licence

MIT. See `LICENSE`.
