# Methodology

What this project measures, what it doesn't, and why the numbers are where they
are.

---

## 1. The honest limitation, first

**Headline sentiment is not public opinion.** This map shows the emotional tone
of what news editors published, not what anyone in that country feels. Four
things sit between the two, and none of them is small:

**Editors choose what runs.** Newsrooms select for conflict, novelty and
consequence, because that's what people read. A calm country with functional
institutions produces a news feed that still skews negative, because the calm
parts aren't news. Every country on this map is measured through that same filter,
which makes comparisons *between* countries more meaningful than any country's
absolute score.

**The source shapes the sample.** Country readings come from whichever outlets
NewsAPI has indexed for that country, which is not a representative sample of
what people there actually read — it over-weights English-language and
digital-native publishers. City readings come from a Google News search, which
returns whatever matches the city's name, including stories merely datelined
there.

**A headline is not its story.** "Death toll rises to 40" and "Death toll revised
down to 40" carry opposite news and similar words. Scoring a single stripped-down
sentence, without the article and without the context of the week, loses a great
deal.

**The model reads words, not situations.** VADER is a lexicon with rules. It
knows "disaster" is negative and "wins" is positive. It does not know that
"markets plunge" is worse than "temperatures plunge", and it will read a sarcastic
headline exactly backwards.

Read the map as *the weather of the news feed*. That's a real thing, it varies
meaningfully by place and by day, and it's worth looking at. It is not a mood ring
for a nation.

---

## 2. Why these thresholds

The bands in `mapping/weather_mapper.py`:

| Condition | Band | Roughly means |
| --- | --- | --- |
| Sunny | `score >= 0.5` | Strongly and consistently positive |
| Partly cloudy | `0.15 <= score < 0.5` | Leaning positive |
| Overcast | `-0.15 <= score < 0.15` | Mixed or neutral |
| Rainy | `-0.5 <= score < -0.15` | Leaning negative |
| Thunderstorm | `score < -0.5` | Strongly and consistently negative |

Three things drove these numbers.

**±0.05 is VADER's own neutral band, but it's far too tight for a mean.** VADER's
documentation suggests treating a single text's compound score as neutral between
-0.05 and +0.05. That's a threshold for one sentence. Here we're averaging twenty
to forty, and averaging pulls hard toward the middle: individually strong
headlines cancel out, and a genuinely mixed feed lands within a few hundredths of
zero. Keeping ±0.05 would have made almost everything overcast. Widening the
neutral band to ±0.15 is a deliberate correction for that compression.

**±0.5 as the outer band is intentionally hard to reach.** A mean of -0.5 across
thirty headlines means the feed is *relentless* — not one bad story among many,
but a whole front page of them. Thunderstorms should be rare enough to be worth
noticing. During normal news cycles most countries land between -0.3 and +0.1, so
the middle three bands do the day-to-day work and the outer two mark genuine
extremes.

**Five bands, because that's what a weather metaphor supports.** Sun, part cloud,
cloud, rain, storm is the vocabulary people already read fluently. A sixth or
seventh would be a distinction nobody could see on a map pin, and would imply
precision the underlying number doesn't have.

Boundaries are lower-inclusive: exactly 0.15 is partly cloudy, not overcast. This
is arbitrary, but the alternative leaves boundary values undefined, and the tests
pin the choice down so it can't drift.

### The thresholds are for VADER

They were set against VADER's score distribution. `HIGH_ACCURACY_MODE` swaps in
DistilBERT SST-2, which is a binary classifier reporting confidence — for most
headlines that's above 0.9, so scores pile up near ±1 and the map polarises. That
mode is worth having to show the tradeoff, but the bands would need retuning to
make it the better choice rather than a different one.

---

## 3. Why country and city use different sources

They answer different questions, and neither source answers both well.

**Countries use NewsAPI's `/top-headlines?country=`.** The question is "what is
the front page in Japan right now", and that requires someone to have already
decided which outlets constitute Japan's front page. NewsAPI has made that call.
Reproducing it with a search query would mean hardcoding a list of outlets per
country and quietly baking in our own editorial judgement about which ones count.

**Countries fall back to RSS when NewsAPI has nothing.** This turned out to
matter more than expected. NewsAPI's non-US `top-headlines` coverage has thinned
over the years, and it now answers `status: ok` with an empty article list for
several supported countries — a successful response carrying no news. Left alone,
those countries stay permanently grey while the rest of the map works.

So an empty or failed NewsAPI response falls through to the same RSS search the
city tier uses, querying the country name. That reading is weaker: a keyword
search is not an editorial front page, and it pulls in international coverage
*about* a country alongside domestic reporting *from* it. Which source answered is
therefore stored and shown in the panel, rather than presenting both as
equivalent.

The side effect is worth having: someone who clones the repo and never registers
for a key still gets a fully working map, because RSS needs no authentication.

**Cities use Google News RSS search.** No free news API has a city parameter —
country is the finest granularity any of them offer. A keyword search is the only
thing that reaches city level at all. It's noisier: searching "Bhopal" returns
stories *about* Bhopal, stories datelined there, and occasionally stories that
merely mention it. That noise is the price of the granularity, and it's why city
names in `regions.json` each carry an explicit `query` string — bare "Birmingham"
pulls Alabama, bare "Perth" pulls Scotland.

The secondary benefit is cost. RSS needs no key and has no published quota, so
drill-down — the interaction people will use most while exploring — doesn't
consume the 100-request daily budget that keeps the world view alive.

---

## 4. How a score is built

1. **Fetch** up to 40 headlines for the region.
2. **Deduplicate** on normalised text. Syndication means one wire story can appear
   a dozen times with only the publisher differing; left alone it gets a dozen
   votes. Identical reprints are caught, genuinely reworded ones aren't.
3. **Strip the publisher suffix.** Titles arrive as "Bridge reopens — Reuters".
   Scored as written, outlet names become part of the region's mood.
4. **Score each headline** independently, giving a compound value in [-1, 1].
5. **Average, unweighted.** Weighting by recency or outlet reach would need data
   the free tiers don't reliably provide, and inventing weights would make the
   number look more authoritative than it is.
6. **Map** the mean onto a condition.

### Confidence

Below 15 headlines a region is flagged `low` confidence, and the UI dims its pin.
The mean of four headlines is dominated by whichever story was loudest that hour;
by twenty it starts to describe the feed rather than a single event. The reading
is still served — hiding it would be worse than showing it with a caveat — but it
shouldn't draw the eye as strongly as a well-covered one.

Unreachable regions are `none` confidence and render as a dashed grey pin. This is
kept strictly distinct from a neutral reading: "we couldn't reach the source" and
"the news was flat" are different facts, and collapsing them would let an outage
masquerade as a calm day.

---

## 5. The 7-day strip

Daily snapshots are written on every refresh, last-write-wins per day. With a
4-hour TTL that means past days show their evening reading rather than a daily
average. Averaging every refresh would smooth away exactly the swings the strip
exists to reveal.

Missing days are left as gaps rather than backfilled with neutral values — a flat
grey square would be indistinguishable from a genuinely neutral day. A new install
shows a one-square strip that grows.

Cities get no strip. They'd need their own snapshot history, and since cities are
only fetched when someone opens them, that history would be a record of when the
site had visitors rather than of the news.

---

## 6. Things worth doing next

- **Compare against a baseline.** A country's score means little in isolation but
  a lot against its own 30-day median. "Unusually stormy for India" is a stronger
  claim than "stormy".
- **Score in the original language.** Everything currently runs through English
  sources or English-language results, which is a real sampling bias for Japan,
  Brazil, Germany and France in particular.
- **Separate topic from tone.** A feed dominated by sport reads differently from
  one dominated by politics at the same sentiment score.
