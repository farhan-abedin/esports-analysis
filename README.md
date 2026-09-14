# Esports Analysis

A set of Python tools that pull competitive Fortnite match data from the
[Osirion](https://osirion.gg) API and turn it into visual analysis of player
behaviour, positioning and endgame decision-making.

Built for content creators and high-level competitive players to answer
questions that standard post-match stats do not cover.

## The tools

### `placementAgainstNetDamage2.py`

Plots team placement against cumulative net damage to show whether damage
actually converts into placement.

A single game renders as a scatter plot, one point per team. Multiple games
render as box plots showing range, IQR, median and mean. The plot is
interactive: hovering a box reveals its mean and median, clicking one prints
the raw team breakdown for that bucket, and bucket size is adjustable live
with a slider. The y axis is deliberately fixed so the shape stays comparable
while scrubbing through a timeline.

### `foottrafficanalyser4.py`

Analyses player movement across the island.

Positions are drawn over the map, and a region of interest is defined by
drawing a polygon directly on the plot. A point-in-polygon test then resolves
which players passed through that area and when, with a range slider to
restrict the time window. Also pulls tournament leaderboards and converts
session IDs into match IDs, so a whole event can be analysed rather than a
hand-listed set of games.

### `healofftimer.py`

Analyses endgame heal-offs. Locates the phase 12 zone timing, then classifies
each heal-off by how long before the zone closed it began, bucketing into
sub-10 second, 10 to 30 second, 30 to 50 second and sickness ranges. Also
tracks the eliminations and level of the winning team.

### `matsovertime.py`

Tracks material counts across a match using inventory update events,
correlated against zone timings, to show how build resources deplete through
the phases of a game.

### `findbosses.py`

Extracts NPC and boss movement paths and plots them over the island map, so
patrol routes and spawn behaviour can be read at a glance.

## Data handling

All five tools share the same approach to the API.

Match data is fetched from Osirion's events endpoint with the specific event
types each tool needs, requested per tool rather than pulling everything:

| Tool | Events requested |
|---|---|
| `placementAgainstNetDamage2` | elimination events |
| `foottrafficanalyser4` | safe zone updates, movement events, players |
| `healofftimer` | safe zone updates, eliminations, players |
| `matsovertime` | inventory updates, safe zone updates, eliminations |
| `findbosses` | NPCs, NPC movement events |

Every response is cached to a local JSON file keyed by match ID, and checked
before any request is made. Repeat analysis of the same match costs nothing,
which matters because a single match produces a large event payload and these
tools are run repeatedly while tuning a visualisation.

## Stack

Python, requests, matplotlib (including its interactive widget layer:
`PolygonSelector`, `RangeSlider`, `Button`) and numpy.

## Configuration

Requires an Osirion API token, supplied as `OSIRION_API_TOKEN`. See
`.env.example` for the variable name.

Map overlays are drawn against `background.jpg` using Fortnite world
coordinates, with the image extent set to the island bounds.
